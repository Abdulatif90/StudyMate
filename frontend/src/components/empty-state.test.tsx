import { render, screen } from "@testing-library/react";
import { BookOpen } from "lucide-react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders the title and description", () => {
    render(
      <EmptyState icon={BookOpen} title="No subjects yet" description="Add one to get started" />
    );
    expect(screen.getByText("No subjects yet")).toBeInTheDocument();
    expect(screen.getByText("Add one to get started")).toBeInTheDocument();
  });

  it("omits the description when none is given", () => {
    render(<EmptyState icon={BookOpen} title="No subjects yet" />);
    expect(screen.queryByText("Add one to get started")).not.toBeInTheDocument();
  });

  it("renders the action when given", () => {
    render(
      <EmptyState icon={BookOpen} title="No subjects yet" action={<button>Create one</button>} />
    );
    expect(screen.getByRole("button", { name: "Create one" })).toBeInTheDocument();
  });
});
