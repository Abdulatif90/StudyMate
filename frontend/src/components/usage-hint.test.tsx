import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UsageHint } from "./usage-hint";
import type { UsageMeter } from "@/lib/planLimits";

function meter(overrides: Partial<UsageMeter> = {}): UsageMeter {
  return {
    key: "subjects",
    used: 1,
    cap: 3,
    unlimited: false,
    percent: 33,
    atLimit: false,
    ...overrides,
  };
}

describe("UsageHint", () => {
  it("renders the given text at normal severity", () => {
    render(<UsageHint meter={meter()} text="1 of 3 subjects used" />);
    const el = screen.getByText("1 of 3 subjects used");
    expect(el).toHaveClass("text-muted-foreground");
  });

  it("uses warning styling near the cap", () => {
    render(<UsageHint meter={meter({ used: 4, cap: 5, percent: 80 })} text="4 of 5 used" />);
    expect(screen.getByText("4 of 5 used")).toHaveClass("text-warning");
  });

  it("uses destructive styling once at the cap", () => {
    render(<UsageHint meter={meter({ used: 3, cap: 3, percent: 100, atLimit: true })} text="3 of 3 used" />);
    expect(screen.getByText("3 of 3 used")).toHaveClass("text-destructive");
  });

  it("renders nothing for an unlimited meter", () => {
    render(<UsageHint meter={meter({ cap: null, unlimited: true })} text="unlimited" />);
    expect(screen.queryByText("unlimited")).not.toBeInTheDocument();
  });
});
