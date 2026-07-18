"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnswerMessage } from "@/components/answer-message";
import { useConfirm } from "@/components/confirm-provider";
import { QuestionMessage } from "@/components/question-message";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { useApiClient } from "@/lib/api/useApiClient";
import { streamAsk } from "@/lib/api/streamAsk";
import { filterConversationsBySubject } from "@/lib/conversationFilter";
import { splitTurnsAtEdit } from "@/lib/editTurn";
import { groupConversationsByDate } from "@/lib/groupConversationsByDate";
import { truncateText } from "@/lib/truncateText";
import type { components } from "@/lib/api/schema";

type Turn = components["schemas"]["ConversationTurnRead"];
type ConversationRead = components["schemas"]["ConversationRead"];
type ConversationWithTurns = components["schemas"]["ConversationWithTurns"];

export default function AskPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const api = useApiClient();
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const confirm = useConfirm();

  const [question, setQuestion] = useState("");
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pinnedTurnIds, setPinnedTurnIds] = useState<Set<string>>(new Set());
  const [editingTurnId, setEditingTurnId] = useState<string | null>(null);
  // The in-flight ask (new question or edit-resend), if any — drives both the
  // pending question bubble and the live-filling answer bubble below it.
  // Otherwise the question/answer the user just (re-)asked has nowhere to
  // appear until the stream finishes, which is especially jarring after an
  // edit (the edited turn was just removed from `turns`, so the transcript
  // would show nothing at all while Claude generates).
  const [streaming, setStreaming] = useState<{ question: string; answer: string } | null>(null);
  const [streamError, setStreamError] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  // Turns removed from view by saveEditedTurn ("regenerate from here"), kept
  // here so they can be put back if the resend fails — otherwise a failed
  // edit/resend would permanently drop the question with no way to recover it.
  const removedTurnsRef = useRef<Turn[]>([]);

  // Aborts any in-flight stream if the user navigates away entirely — the
  // server keeps generating and still saves the turn (see service.stream_answer's
  // docstring), this just stops updating state for a component that's gone.
  useEffect(() => {
    return () => abortControllerRef.current?.abort();
  }, []);

  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: async () => {
      const { data, error } = await api.GET("/conversations");
      if (error) throw error;
      return data;
    },
  });

  const subjectConversations = filterConversationsBySubject(
    conversationsQuery.data ?? [],
    subjectId
  ).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  // Fetched for every conversation in the sidebar (not just the active one) so
  // each item can show a real preview of its first question — like Claude's own
  // sidebar — without a per-item timestamp. Also means clicking one to open it
  // is instant, since its turns are already loaded.
  const conversationDetailsQueries = useQueries({
    queries: subjectConversations.map((conversation) => ({
      queryKey: ["conversations", conversation.id],
      queryFn: async (): Promise<ConversationWithTurns> => {
        const { data, error } = await api.GET("/conversations/{conversation_id}", {
          params: { path: { conversation_id: conversation.id } },
        });
        if (error) throw error;
        return data;
      },
    })),
  });

  const conversationDetailsById = new Map<string, ConversationWithTurns | undefined>(
    subjectConversations.map((conversation, index) => [
      conversation.id,
      conversationDetailsQueries[index]?.data,
    ])
  );

  function conversationPreview(conversation: ConversationRead): string {
    const details = conversationDetailsById.get(conversation.id);
    const label = conversation.title ?? details?.turns[0]?.question ?? "New conversation";
    return truncateText(label, 40);
  }

  const deleteConversation = useMutation({
    mutationFn: async (conversationId: string) => {
      const { error } = await api.DELETE("/conversations/{conversation_id}", {
        params: { path: { conversation_id: conversationId } },
      });
      if (error) throw error;
    },
    onSuccess: (_data, conversationId) => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      queryClient.removeQueries({ queryKey: ["conversations", conversationId] });
      if (activeConversationId === conversationId) {
        setActiveConversationId(null);
        setTurns([]);
      }
      toast.success("Conversation deleted");
    },
    onError: () => {
      toast.error("Couldn't delete conversation", "Please try again.");
    },
  });

  // Drives POST /subjects/{subject_id}/ask/stream — used for both a plain new
  // question and an edit-resend. `fullAnswer` is accumulated in this closure
  // (not read back from `streaming` state) so the "done" handler always has the
  // exact final text, regardless of React state-update timing.
  function startAsk(questionText: string) {
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setStreamError(false);
    setStreaming({ question: questionText, answer: "" });

    let fullAnswer = "";
    streamAsk(
      { subjectId, question: questionText, conversationId: activeConversationId, getToken },
      {
        onToken: (delta) => {
          fullAnswer += delta;
          setStreaming({ question: questionText, answer: fullAnswer });
        },
        onDone: (data) => {
          removedTurnsRef.current = [];
          setActiveConversationId(data.conversation_id);
          setTurns((prev) => [
            ...prev,
            {
              id: data.turn_id,
              question: questionText,
              answer: fullAnswer,
              sources: data.sources,
              created_at: new Date().toISOString(),
            },
          ]);
          // Cleared here, in the same handler that appends the real turn — not
          // on some later tick — so the streaming bubble disappears in the same
          // update the finished turn appears in, instead of both being on
          // screen for a render.
          setStreaming(null);
          queryClient.invalidateQueries({ queryKey: ["conversations"] });
          queryClient.invalidateQueries({ queryKey: ["conversations", data.conversation_id] });
        },
      },
      controller.signal
    ).catch(() => {
      if (controller.signal.aborted) return; // deliberate cancel, not a failure
      if (removedTurnsRef.current.length > 0) {
        setTurns((prev) => [...prev, ...removedTurnsRef.current]);
        removedTurnsRef.current = [];
      } else {
        // Not an edit-resend — the compose box was already cleared on submit,
        // so put the text back rather than losing it.
        setQuestion(questionText);
      }
      setStreamError(true);
      setStreaming(null);
    });
  }

  // Switching conversations mid-stream would otherwise keep filling in an
  // answer bubble for a conversation the user already left — abort it. The
  // server-side generation/persistence continues regardless (see startAsk).
  function abortActiveStream() {
    abortControllerRef.current?.abort();
    setStreaming(null);
    setStreamError(false);
  }

  function selectConversation(conversationId: string) {
    const details = conversationDetailsById.get(conversationId);
    abortActiveStream();
    setActiveConversationId(conversationId);
    setTurns(details?.turns ?? []);
    setEditingTurnId(null);
    removedTurnsRef.current = [];
  }

  function startNewConversation() {
    abortActiveStream();
    setActiveConversationId(null);
    setTurns([]);
    setEditingTurnId(null);
    removedTurnsRef.current = [];
  }

  function startEditingTurn(turnId: string) {
    if (streaming) return; // avoid editing another turn while one is in flight
    setEditingTurnId(turnId);
  }

  function cancelEditingTurn() {
    setEditingTurnId(null);
  }

  // Editing a question resends it in the SAME conversation (not a new one) —
  // this stays within the current session. The backend has no endpoint to
  // edit/delete a single turn, only whole conversations, so this is
  // implemented as: drop the edited turn and everything after it from the
  // visible transcript (like "regenerate from here"), then ask again with the
  // edited text and the same conversation_id, which appends a fresh turn.
  // The old turn (and anything that followed it) still exists server-side —
  // it'll resurface if this conversation is reloaded from the sidebar, and
  // Claude's context for the new answer may still include it, since the
  // backend has no way to know a turn was "replaced" rather than just
  // followed-up on.
  function saveEditedTurn(turnId: string, newQuestionText: string) {
    const { remaining, removed } = splitTurnsAtEdit(turns, turnId);
    setTurns(remaining);
    removedTurnsRef.current = removed;
    setEditingTurnId(null);
    startAsk(newQuestionText);
  }

  // No backend endpoint exists to delete a single turn (only whole
  // conversations, via DELETE /conversations/{id}) — this only removes it from
  // the current view. Reloading this conversation from the sidebar will bring
  // it back, since nothing is deleted server-side.
  function deleteQuestionLocally(turnId: string) {
    setTurns((prev) => prev.filter((turn) => turn.id !== turnId));
  }

  function togglePin(turnId: string) {
    setPinnedTurnIds((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) {
        next.delete(turnId);
      } else {
        next.add(turnId);
      }
      return next;
    });
  }

  const conversationGroups = groupConversationsByDate(subjectConversations);

  return (
    <div className="flex flex-col gap-6 md:flex-row">
      <aside className="shrink-0 border-b pb-6 md:w-56 md:border-b-0 md:pb-0">
        <Link
          href={`/subjects/${subjectId}`}
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Subject
        </Link>

        <Button
          variant="outline"
          className="mb-4 w-full"
          onClick={startNewConversation}
          disabled={activeConversationId === null && turns.length === 0}
        >
          New conversation
        </Button>

        <p className="mb-2 text-xs font-medium text-muted-foreground">Conversations</p>
        {conversationsQuery.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {subjectConversations.length === 0 && !conversationsQuery.isLoading && (
          <p className="text-sm text-muted-foreground">No conversations yet.</p>
        )}
        <div className="max-h-40 overflow-y-auto md:max-h-none md:overflow-visible">
          {conversationGroups.map((group) => (
            <div key={group.label} className="mb-3 last:mb-0">
              <p className="mb-1 text-xs font-medium text-muted-foreground">{group.label}</p>
              <ul className="flex flex-col gap-1">
                {group.conversations.map((conversation) => (
                  <li key={conversation.id} className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => selectConversation(conversation.id)}
                      className={`min-w-0 flex-1 truncate rounded-lg px-2 py-1 text-left text-sm hover:bg-muted ${
                        activeConversationId === conversation.id ? "bg-muted font-medium" : ""
                      }`}
                    >
                      {conversationPreview(conversation)}
                    </button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="shrink-0"
                      aria-label="Delete conversation"
                      onClick={async () => {
                        const ok = await confirm({
                          title: "Delete this conversation?",
                          destructive: true,
                        });
                        if (!ok) return;
                        deleteConversation.mutate(conversation.id);
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <h1 className="mb-4 text-2xl font-semibold">Ask</h1>

        <ul className="mb-4 flex flex-col gap-3">
          {turns.map((turn) => (
            <li key={turn.id} className="flex flex-col gap-2">
              <QuestionMessage
                text={turn.question}
                timestamp={turn.created_at}
                isEditing={editingTurnId === turn.id}
                onStartEdit={() => startEditingTurn(turn.id)}
                onCancelEdit={cancelEditingTurn}
                onSaveEdit={(newText) => saveEditedTurn(turn.id, newText)}
                onDelete={() => deleteQuestionLocally(turn.id)}
              />
              <AnswerMessage
                text={turn.answer}
                timestamp={turn.created_at}
                pinned={pinnedTurnIds.has(turn.id)}
                onTogglePin={() => togglePin(turn.id)}
              />
            </li>
          ))}
          {streaming && (
            <li className="flex flex-col gap-2">
              <QuestionMessage
                text={streaming.question}
                timestamp={new Date().toISOString()}
                isEditing={false}
                pending
                onStartEdit={() => {}}
                onCancelEdit={() => {}}
                onSaveEdit={() => {}}
                onDelete={() => {}}
              />
              {streaming.answer && (
                <AnswerMessage
                  text={streaming.answer}
                  timestamp={new Date().toISOString()}
                  pinned={false}
                  onTogglePin={() => {}}
                  streaming
                />
              )}
            </li>
          )}
        </ul>

        {!streaming && (
          <form
            className="flex flex-col gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const trimmed = question.trim();
              if (trimmed) {
                setQuestion("");
                startAsk(trimmed);
              }
            }}
          >
            <Textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a question about this subject's materials…"
            />
            <Button type="submit" className="self-end" disabled={!question.trim()}>
              Send
            </Button>
          </form>
        )}
        {streaming && !streaming.answer && (
          <p className="mt-2 text-sm text-muted-foreground">
            Thinking… this can take a few seconds.
          </p>
        )}
        {streamError && (
          <p className="mt-2 text-sm text-destructive">
            Couldn&apos;t get an answer. Please try again.
          </p>
        )}
      </main>
    </div>
  );
}
