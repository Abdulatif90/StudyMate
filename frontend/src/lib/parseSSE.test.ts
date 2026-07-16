import { describe, expect, it } from "vitest";
import { createSSEParser } from "./parseSSE";

describe("createSSEParser", () => {
  it("parses a single complete event", () => {
    const parser = createSSEParser();
    const events = parser.push('event: token\ndata: {"text":"Hi"}\n\n');
    expect(events).toEqual([{ event: "token", data: '{"text":"Hi"}' }]);
  });

  it("parses multiple events delivered in one chunk", () => {
    const parser = createSSEParser();
    const events = parser.push(
      'event: token\ndata: {"text":"A"}\n\nevent: token\ndata: {"text":"B"}\n\n'
    );
    expect(events).toEqual([
      { event: "token", data: '{"text":"A"}' },
      { event: "token", data: '{"text":"B"}' },
    ]);
  });

  it("carries a partial event across chunk boundaries", () => {
    const parser = createSSEParser();
    expect(parser.push('event: tok')).toEqual([]);
    expect(parser.push('en\ndata: {"text":"Hi"}\n\n')).toEqual([
      { event: "token", data: '{"text":"Hi"}' },
    ]);
  });

  it("carries a partial event even when it splits mid-line across three chunks", () => {
    const parser = createSSEParser();
    expect(parser.push("event: token\ndata: {")).toEqual([]);
    expect(parser.push('"text":"Hi')).toEqual([]);
    expect(parser.push('"}\n\n')).toEqual([{ event: "token", data: '{"text":"Hi"}' }]);
  });

  it("returns events found so far and buffers the rest when a chunk has both", () => {
    const parser = createSSEParser();
    const events = parser.push('event: token\ndata: {"text":"A"}\n\nevent: done\ndata: {"x":1');
    expect(events).toEqual([{ event: "token", data: '{"text":"A"}' }]);

    const rest = parser.push('}\n\n');
    expect(rest).toEqual([{ event: "done", data: '{"x":1}' }]);
  });

  it("defaults the event name to 'message' when none is given", () => {
    const parser = createSSEParser();
    const events = parser.push('data: {"text":"Hi"}\n\n');
    expect(events).toEqual([{ event: "message", data: '{"text":"Hi"}' }]);
  });
});
