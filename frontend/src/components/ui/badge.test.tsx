import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";

describe("Badge", () => {
  it("renders its children", () => {
    render(<Badge>ready</Badge>);
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("applies the variant's class", () => {
    render(<Badge variant="destructive">failed</Badge>);
    expect(screen.getByText("failed")).toHaveClass("text-destructive");
  });
});
