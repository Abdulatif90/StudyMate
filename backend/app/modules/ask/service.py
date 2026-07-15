"""Business logic for the Ask endpoint: retrieve relevant chunks, ask Claude, cite
sources, and persist the exchange as a ConversationTurn. Graceful degradation is
handled entirely here, not in the router — "no relevant material" and "Claude
failed" both return a normal 200 `AskResponse` with an explanatory `answer`, rather
than an HTTP error, and the turn is still saved either way (the task's transcript
should show what was actually asked and answered, even when generation failed). The
exceptions that do propagate up (`SubjectNotFoundError`, `ConversationNotFoundError`)
are translated to 404 by the router.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.modules.ask.llm import LLMError, ask_claude
from app.modules.ask.models import Conversation, ConversationTurn
from app.modules.ask.schemas import AskResponse, SourceChunk
from app.modules.documents.service import get_documents_by_ids, require_owned_subject, search_chunks

TOP_K = 8
# How many of a conversation's most recent turns to feed Claude as history. list_turns
# (used by GET /conversations/{id}) returns the *full* transcript regardless — this
# only caps what's sent to the model, for token/cost reasons.
MAX_CONTEXT_TURNS = 10

_NO_MATERIAL_ANSWER = (
    "I couldn't find any relevant material in this subject to answer that question."
)
_GENERATION_FAILED_ANSWER = (
    "I found relevant material, but couldn't generate an answer right now. Please try again."
)


class ConversationNotFoundError(Exception):
    """Raised when the given conversation doesn't exist, isn't owned by the caller,
    or doesn't belong to the subject it was asked about."""


def create_conversation(
    session: Session, owner_id: str, subject_id: uuid.UUID, title: str | None = None
) -> Conversation:
    conversation = Conversation(subject_id=subject_id, owner_id=owner_id, title=title)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def get_conversation(
    session: Session, owner_id: str, conversation_id: uuid.UUID
) -> Conversation | None:
    return session.exec(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == owner_id
        )
    ).first()


def list_conversations(session: Session, owner_id: str) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.owner_id == owner_id)
            .order_by(Conversation.created_at.desc())
        )
    )


def list_turns(
    session: Session, owner_id: str, conversation_id: uuid.UUID
) -> list[ConversationTurn]:
    return list(
        session.exec(
            select(ConversationTurn)
            .where(
                ConversationTurn.conversation_id == conversation_id,
                ConversationTurn.owner_id == owner_id,
            )
            .order_by(ConversationTurn.created_at)
        )
    )


def create_turn(
    session: Session,
    owner_id: str,
    conversation_id: uuid.UUID,
    question: str,
    answer: str,
    sources: list[SourceChunk],
) -> ConversationTurn:
    turn = ConversationTurn(
        conversation_id=conversation_id,
        owner_id=owner_id,
        question=question,
        answer=answer,
        sources=[source.model_dump(mode="json") for source in sources],
    )
    session.add(turn)
    session.commit()
    session.refresh(turn)
    return turn


def delete_conversation(session: Session, owner_id: str, conversation_id: uuid.UUID) -> bool:
    conversation = get_conversation(session, owner_id, conversation_id)
    if conversation is None:
        return False
    for turn in list_turns(session, owner_id, conversation_id):
        session.delete(turn)
    # Flush before deleting the parent: there's no ORM-level relationship()/cascade
    # between Conversation and ConversationTurn (just a plain FK column, matching this
    # codebase's style elsewhere), so SQLAlchemy's flush doesn't know these deletes
    # are order-dependent — without this, it can emit the DELETE FROM conversations
    # before DELETE FROM conversation_turns and hit the FK constraint. Confirmed this
    # was a real failure, not a hypothetical one, via the live end-to-end test.
    session.flush()
    session.delete(conversation)
    session.commit()
    return True


def ask_question(
    session: Session,
    owner_id: str,
    subject_id: uuid.UUID,
    question: str,
    conversation_id: uuid.UUID | None = None,
) -> AskResponse:
    require_owned_subject(session, owner_id, subject_id)

    if conversation_id is not None:
        conversation = get_conversation(session, owner_id, conversation_id)
        if conversation is None or conversation.subject_id != subject_id:
            raise ConversationNotFoundError(conversation_id)
    else:
        conversation = create_conversation(session, owner_id, subject_id)

    prior_turns = list_turns(session, owner_id, conversation.id)[-MAX_CONTEXT_TURNS:]
    prior_turns_context = [{"question": t.question, "answer": t.answer} for t in prior_turns]

    results = search_chunks(session, owner_id, subject_id, question, top_k=TOP_K)

    if not results:
        answer = _NO_MATERIAL_ANSWER
        sources: list[SourceChunk] = []
    else:
        document_ids = list({chunk.document_id for chunk, _score in results})
        documents_by_id = get_documents_by_ids(session, owner_id, document_ids)
        context_chunks = [
            {
                "filename": documents_by_id[chunk.document_id].filename,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
            }
            for chunk, _score in results
        ]
        try:
            answer = ask_claude(question, context_chunks, prior_turns=prior_turns_context)
            sources = [
                SourceChunk(
                    document_id=chunk.document_id,
                    filename=documents_by_id[chunk.document_id].filename,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    similarity_score=score,
                )
                for chunk, score in results
            ]
        except LLMError:
            answer = _GENERATION_FAILED_ANSWER
            sources = []

    create_turn(session, owner_id, conversation.id, question, answer, sources)

    return AskResponse(answer=answer, sources=sources, conversation_id=conversation.id)
