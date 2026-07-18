import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithIntl } from "@/lib/test/renderWithIntl";
import { UsageStatCard } from "./usage-stat-card";
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

describe("UsageStatCard", () => {
  it("shows used/cap in green when healthy", () => {
    renderWithIntl(<UsageStatCard meter={meter()} />);
    expect(screen.getByText("1/3")).toHaveClass("text-success");
  });

  it("shows used/cap in amber near the cap", () => {
    renderWithIntl(<UsageStatCard meter={meter({ used: 4, cap: 5, percent: 80 })} />);
    expect(screen.getByText("4/5")).toHaveClass("text-warning");
  });

  it("shows the infinity symbol with no progress bar for an unlimited meter", () => {
    renderWithIntl(<UsageStatCard meter={meter({ cap: null, unlimited: true })} />);
    expect(screen.getByText("∞")).toBeInTheDocument();
  });
});
