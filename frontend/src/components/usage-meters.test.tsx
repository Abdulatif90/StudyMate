import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UsageMeters } from "./usage-meters";
import type { components } from "@/lib/api/schema";

type PlanRead = components["schemas"]["PlanRead"];

function planRead(overrides: Partial<PlanRead> = {}): PlanRead {
  return {
    plan: "free",
    limits: {
      max_subjects: 3,
      max_documents_per_subject: 10,
      max_generations_per_day: 20,
    },
    usage: { subjects: 2, generations_today: 5 },
    ...overrides,
  };
}

describe("UsageMeters", () => {
  it("shows 'used of cap' text and a bar for a finite cap", () => {
    render(<UsageMeters plan={planRead()} />);
    expect(screen.getByText("2 of 3 used")).toBeInTheDocument();
    // Bar exposed as an image with the same used/cap in its label (never colour alone).
    expect(
      screen.getByRole("img", { name: "Subjects: 2 of 3 used" }),
    ).toBeInTheDocument();
  });

  it("shows an unlimited count with no bar for a null cap", () => {
    render(
      <UsageMeters
        plan={planRead({
          plan: "business",
          limits: {
            max_subjects: null,
            max_documents_per_subject: null,
            max_generations_per_day: null,
          },
          usage: { subjects: 12, generations_today: 40 },
        })}
      />,
    );
    expect(screen.getByText("12 · Unlimited")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
