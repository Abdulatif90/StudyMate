import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SubjectCard } from "./subject-card";

describe("SubjectCard", () => {
  it("links to the subject and shows its name and meta line", () => {
    render(<SubjectCard href="/subjects/abc" name="Biology" meta="3 documents · 2 due" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/subjects/abc");
    expect(screen.getByText("Biology")).toBeInTheDocument();
    expect(screen.getByText("3 documents · 2 due")).toBeInTheDocument();
  });

  it("keeps an optional trailing action OUTSIDE the link, not nested inside it", () => {
    render(
      <SubjectCard
        href="/subjects/abc"
        name="Biology"
        meta="3 documents"
        action={<button>Delete</button>}
      />,
    );
    const link = screen.getByRole("link");
    const deleteButton = screen.getByRole("button", { name: "Delete" });
    expect(link).not.toContainElement(deleteButton);
  });
});
