import { createSSEParser } from "@/lib/parseSSE";
import type { components } from "@/lib/api/schema";

type SourceChunk = components["schemas"]["SourceChunk"];

/** Same origin FastAPI is served from — see lib/api/client.ts. Duplicated rather
 * than imported from there because this call deliberately bypasses openapi-fetch
 * (it has no support for a streamed response body, only parsed JSON). */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type StreamAskDoneData = {
  conversation_id: string;
  turn_id: string;
  sources: SourceChunk[];
};

export type StreamAskHandlers = {
  onToken: (text: string) => void;
  onDone: (data: StreamAskDoneData) => void;
};

/**
 * Drives POST /subjects/{subject_id}/ask/stream. `EventSource` can't attach the
 * Clerk bearer token (it only ever sends a GET with no custom headers), so this
 * uses `fetch()` + a manual `ReadableStream` reader instead, attaching the token
 * the same way `useApiClient`'s middleware does for the typed client.
 *
 * Rejects on a non-2xx response, a network failure, or `signal` firing (an
 * `AbortError`) — the caller is expected to check `signal.aborted` in its catch to
 * tell a deliberate cancel apart from a real failure.
 */
export async function streamAsk(
  params: {
    subjectId: string;
    question: string;
    conversationId: string | null;
    getToken: () => Promise<string | null>;
  },
  handlers: StreamAskHandlers,
  signal: AbortSignal
): Promise<void> {
  const token = await params.getToken();

  const response = await fetch(`${API_BASE_URL}/subjects/${params.subjectId}/ask/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question: params.question,
      conversation_id: params.conversationId ?? undefined,
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Ask stream request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser();

  while (true) {
    const { done, value } = await reader.read();
    if (done) return;

    const chunk = decoder.decode(value, { stream: true });
    for (const { event, data } of parser.push(chunk)) {
      if (event === "token") {
        handlers.onToken((JSON.parse(data) as { text: string }).text);
      } else if (event === "done") {
        handlers.onDone(JSON.parse(data) as StreamAskDoneData);
      }
    }
  }
}
