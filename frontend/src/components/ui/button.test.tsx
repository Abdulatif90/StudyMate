import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders the default variant with the brand gradient fill", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("bg-gradient-brand");
  });

  it("scales down on press, per the design system's interaction rule", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass(
      "active:not-aria-[haspopup]:scale-[0.97]",
    );
  });

  it("keeps the outline variant available for secondary ('ghost') actions", () => {
    render(<Button variant="outline">Cancel</Button>);
    const button = screen.getByRole("button", { name: "Cancel" });
    expect(button).not.toHaveClass("bg-gradient-brand");
    expect(button).toHaveClass("border-border");
  });
});
