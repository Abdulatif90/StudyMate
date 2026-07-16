import { describe, expect, it } from "vitest";
import { splitTurnsAtEdit } from "./editTurn";

function makeTurn(id: string) {
  return {
    id,
    question: `question ${id}`,
    answer: `answer ${id}`,
    sources: [],
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("splitTurnsAtEdit", () => {
  it("keeps turns before the edited one, removes it and everything after", () => {
    const turns = [makeTurn("t1"), makeTurn("t2"), makeTurn("t3")];

    const { remaining, removed } = splitTurnsAtEdit(turns, "t2");

    expect(remaining.map((t) => t.id)).toEqual(["t1"]);
    expect(removed.map((t) => t.id)).toEqual(["t2", "t3"]);
  });

  it("removes everything when editing the first turn", () => {
    const turns = [makeTurn("t1"), makeTurn("t2")];

    const { remaining, removed } = splitTurnsAtEdit(turns, "t1");

    expect(remaining).toEqual([]);
    expect(removed.map((t) => t.id)).toEqual(["t1", "t2"]);
  });

  it("removes nothing when editing the last turn", () => {
    const turns = [makeTurn("t1"), makeTurn("t2")];

    const { remaining, removed } = splitTurnsAtEdit(turns, "t2");

    expect(remaining.map((t) => t.id)).toEqual(["t1"]);
    expect(removed.map((t) => t.id)).toEqual(["t2"]);
  });

  it("removes nothing and keeps the full list when turnId isn't found", () => {
    const turns = [makeTurn("t1"), makeTurn("t2")];

    const { remaining, removed } = splitTurnsAtEdit(turns, "missing");

    expect(remaining).toEqual(turns);
    expect(removed).toEqual([]);
  });

  it("handles an empty transcript", () => {
    expect(splitTurnsAtEdit([], "t1")).toEqual({ remaining: [], removed: [] });
  });
});
