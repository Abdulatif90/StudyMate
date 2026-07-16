export type SSEEvent = { event: string; data: string };

/**
 * Incremental parser for the exact SSE shape the backend's ask/stream endpoint
 * emits (`event: <name>\ndata: <json>\n\n`) — not a general-purpose SSE parser
 * (no multi-line `data:` fields, no `id:`/`retry:`, no comment lines). Built as a
 * stateful `push` because `fetch()`'s `ReadableStream` delivers arbitrary byte
 * chunks that can split an event (or even a single line) across chunk boundaries;
 * `push` buffers any incomplete trailing event and carries it into the next call.
 */
export function createSSEParser() {
  let buffer = "";

  function push(chunk: string): SSEEvent[] {
    buffer += chunk;
    const events: SSEEvent[] = [];

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = "message";
      let data = "";
      for (const line of rawEvent.split("\n")) {
        if (line.startsWith("event: ")) {
          event = line.slice("event: ".length);
        } else if (line.startsWith("data: ")) {
          data = line.slice("data: ".length);
        }
      }
      events.push({ event, data });

      boundary = buffer.indexOf("\n\n");
    }

    return events;
  }

  return { push };
}
