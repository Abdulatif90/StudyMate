import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UpgradePrompt } from "./upgrade-prompt";

describe("UpgradePrompt", () => {
  it("shows the backend message and a link to the billing page", () => {
    render(<UpgradePrompt message="You've reached your free plan limit of 3 subjects." />);
    expect(
      screen.getByText("You've reached your free plan limit of 3 subjects."),
    ).toBeInTheDocument();
    // Base UI's Button renders the link with role="button", so query by that role.
    expect(screen.getByRole("button", { name: "Upgrade" })).toHaveAttribute(
      "href",
      "/billing",
    );
  });
});
