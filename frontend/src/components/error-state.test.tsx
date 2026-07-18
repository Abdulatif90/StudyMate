import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "./error-state";

describe("ErrorState", () => {
  it("renders the message", () => {
    render(<ErrorState message="Couldn't load subjects." />);
    expect(screen.getByText("Couldn't load subjects.")).toBeInTheDocument();
  });

  it("omits the retry button when onRetry isn't given", () => {
    render(<ErrorState message="Couldn't load subjects." />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Couldn't load subjects." retryLabel="Retry" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
