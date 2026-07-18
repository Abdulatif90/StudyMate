import { act, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnimatedProgressBar } from "./animated-progress-bar";

function nextFrame() {
  return new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
}

describe("AnimatedProgressBar", () => {
  it("starts at 0% and animates to the target width after mount", async () => {
    const { container } = render(<AnimatedProgressBar percent={60} />);
    const fill = container.querySelector('[data-slot="progress-fill"]') as HTMLElement;
    expect(fill.style.width).toBe("0%");

    await act(async () => {
      await nextFrame();
    });

    expect(fill.style.width).toBe("60%");
  });

  it("re-animates when the target percent changes", async () => {
    const { container, rerender } = render(<AnimatedProgressBar percent={20} />);
    await act(async () => {
      await nextFrame();
    });
    const fill = container.querySelector('[data-slot="progress-fill"]') as HTMLElement;
    expect(fill.style.width).toBe("20%");

    rerender(<AnimatedProgressBar percent={90} />);
    await act(async () => {
      await nextFrame();
    });
    expect(fill.style.width).toBe("90%");
  });
});
