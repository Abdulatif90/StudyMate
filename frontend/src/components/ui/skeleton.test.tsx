import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("renders a decorative, aria-hidden block sized by the caller's className", () => {
    const { container } = render(<Skeleton className="h-4 w-32" data-testid="line" />);
    const el = container.querySelector('[data-slot="skeleton"]');
    expect(el).toHaveAttribute("aria-hidden");
    expect(el).toHaveClass("h-4", "w-32", "animate-pulse");
  });
});
