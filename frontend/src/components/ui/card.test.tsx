import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./card";

describe("Card", () => {
  it("stays static (no cursor-pointer/hover elevation) by default", () => {
    render(<Card>content</Card>);
    const card = screen.getByText("content");
    expect(card).not.toHaveClass("cursor-pointer");
  });

  it("gains hover elevation and cursor-pointer when interactive", () => {
    render(<Card interactive>content</Card>);
    const card = screen.getByText("content");
    expect(card).toHaveClass("cursor-pointer", "hover:shadow-md");
  });

  it("gains a persistent accent ring when selected", () => {
    render(<Card interactive selected>content</Card>);
    const card = screen.getByText("content");
    expect(card).toHaveClass("ring-2", "ring-primary");
  });
});
