import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithIntl } from "@/lib/test/renderWithIntl";
import { QuestionMessage } from "./question-message";

function renderMessage(overrides: Partial<Parameters<typeof QuestionMessage>[0]> = {}) {
  return renderWithIntl(
    <QuestionMessage
      text="What is photosynthesis?"
      timestamp={new Date().toISOString()}
      isEditing={false}
      onStartEdit={() => {}}
      onCancelEdit={() => {}}
      onSaveEdit={() => {}}
      onDelete={() => {}}
      {...overrides}
    />
  );
}

describe("QuestionMessage", () => {
  it("renders the question text", () => {
    renderMessage();
    expect(screen.getByText("What is photosynthesis?")).toBeInTheDocument();
  });

  it("calls onStartEdit when the edit button is clicked", async () => {
    const onStartEdit = vi.fn();
    renderMessage({ onStartEdit });
    await userEvent.click(screen.getByRole("button", { name: "Edit question" }));
    expect(onStartEdit).toHaveBeenCalledOnce();
  });

  it("calls onDelete when the delete button is clicked", async () => {
    const onDelete = vi.fn();
    renderMessage({ onDelete });
    await userEvent.click(screen.getByRole("button", { name: "Delete question" }));
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("shows an inline editable textarea when isEditing is true, seeded with the current text", () => {
    renderMessage({ isEditing: true });
    expect(screen.getByRole("textbox")).toHaveValue("What is photosynthesis?");
  });

  it("calls onSaveEdit with the edited text, trimmed", async () => {
    const onSaveEdit = vi.fn();
    renderMessage({ isEditing: true, onSaveEdit });
    const textarea = screen.getByRole("textbox");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "  What is chlorophyll?  ");
    await userEvent.click(screen.getByRole("button", { name: "Save & resend" }));
    expect(onSaveEdit).toHaveBeenCalledWith("What is chlorophyll?");
  });

  it("calls onCancelEdit when Cancel is clicked", async () => {
    const onCancelEdit = vi.fn();
    renderMessage({ isEditing: true, onCancelEdit });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancelEdit).toHaveBeenCalledOnce();
  });
});
