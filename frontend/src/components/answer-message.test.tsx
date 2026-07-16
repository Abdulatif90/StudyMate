import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerMessage } from "./answer-message";

describe("AnswerMessage", () => {
  it("renders markdown (bold)", () => {
    render(
      <AnswerMessage
        text="**Revenue** grew significantly."
        timestamp={new Date().toISOString()}
        pinned={false}
        onTogglePin={() => {}}
      />
    );

    const bold = screen.getByText("Revenue");
    expect(bold.tagName).toBe("STRONG");
    expect(screen.getByText(/grew significantly\./)).toBeInTheDocument();
  });

  it("keeps the filename in inline citations but drops the chunk number", () => {
    render(
      <AnswerMessage
        text="Revenue grew (portfolio eng.pdf, chunk 3) significantly."
        timestamp={new Date().toISOString()}
        pinned={false}
        onTogglePin={() => {}}
      />
    );

    expect(screen.getByText(/\(portfolio eng\.pdf\)/)).toBeInTheDocument();
    expect(screen.queryByText(/chunk 3/)).not.toBeInTheDocument();
  });
});
