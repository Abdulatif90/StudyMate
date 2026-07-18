import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PlanCard } from "./plan-card";

describe("PlanCard", () => {
  it("renders name, price, and features, and calls onCta when clicked", () => {
    const onCta = vi.fn();
    render(
      <PlanCard
        name="Pro"
        price="$20"
        priceSuffix="/month"
        features={["50 subjects", "200 documents each"]}
        ctaLabel="Upgrade to Pro"
        onCta={onCta}
      />,
    );
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("$20")).toBeInTheDocument();
    expect(screen.getByText("50 subjects")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Upgrade to Pro" }));
    expect(onCta).toHaveBeenCalledOnce();
  });

  it("shows the popular badge only when popular is set", () => {
    render(
      <PlanCard
        name="Pro"
        price="$20"
        priceSuffix="/month"
        features={[]}
        ctaLabel="Upgrade"
        popular
        popularLabel="Most popular"
      />,
    );
    expect(screen.getByText("Most popular")).toBeInTheDocument();
  });

  it("renders the CTA as a real link when ctaHref is given", () => {
    render(
      <PlanCard
        name="Free"
        price="$0"
        priceSuffix=""
        features={[]}
        ctaLabel="Get started free"
        ctaHref="/sign-up"
      />,
    );
    expect(screen.getByRole("button", { name: "Get started free" })).toHaveAttribute(
      "href",
      "/sign-up",
    );
  });

  it("shows the description line when given", () => {
    render(
      <PlanCard
        name="Pro"
        price="$20"
        priceSuffix="/month"
        description="For serious, regular studying."
        features={[]}
        ctaLabel="Upgrade"
      />,
    );
    expect(screen.getByText("For serious, regular studying.")).toBeInTheDocument();
  });

  it("disables the CTA and shows an outline button for the current plan", () => {
    render(
      <PlanCard
        name="Free"
        price="$0"
        priceSuffix="/month"
        features={[]}
        ctaLabel="Current plan"
        isCurrent
      />,
    );
    expect(screen.getByRole("button", { name: "Current plan" })).toBeDisabled();
  });
});
