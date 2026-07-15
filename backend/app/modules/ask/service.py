"""Business logic for the Ask endpoint: retrieve relevant chunks, ask Claude, cite
sources. Graceful degradation is handled entirely here, not in the router — both "no
relevant material" and "Claude failed" return a normal 200 `AskResponse` with an
explanatory `answer`, rather than an HTTP error. The only exception that propagates
up is `SubjectNotFoundError` (from `search_chunks`), which the router turns into 404.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session

from app.modules.ask.llm import LLMError, ask_claude
from app.modules.ask.schemas import AskResponse, SourceChunk
from app.modules.documents.service import get_documents_by_ids, search_chunks

TOP_K = 8

_NO_MATERIAL_ANSWER = (
    "I couldn't find any relevant material in this subject to answer that question."
)
_GENERATION_FAILED_ANSWER = (
    "I found relevant material, but couldn't generate an answer right now. Please try again."
)


def ask_question(
    session: Session, owner_id: str, subject_id: uuid.UUID, question: str
) -> AskResponse:
    results = search_chunks(session, owner_id, subject_id, question, top_k=TOP_K)

    if not results:
        return AskResponse(answer=_NO_MATERIAL_ANSWER, sources=[])

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
        answer = ask_claude(question, context_chunks)
    except LLMError:
        return AskResponse(answer=_GENERATION_FAILED_ANSWER, sources=[])

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
    return AskResponse(answer=answer, sources=sources)
