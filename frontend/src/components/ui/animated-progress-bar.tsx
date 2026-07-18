"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface AnimatedProgressBarProps {
  /** 0–100. */
  percent: number;
  trackClassName?: string;
  fillClassName?: string;
  className?: string;
}

/**
 * A progress track whose fill animates from 0 to `percent` once, on mount/first data
 * arrival — never an instant jump (design prompt's "animate width... not instant" rule
 * for usage bars). Renders at 0% on the first paint, then transitions to the real value
 * one animation frame later; the CSS `transition` on `width` does the actual easing.
 */
export function AnimatedProgressBar({
  percent,
  trackClassName,
  fillClassName,
  className,
}: AnimatedProgressBarProps) {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setWidth(percent));
    return () => cancelAnimationFrame(frame);
  }, [percent]);

  return (
    <div
      data-slot="progress-track"
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", trackClassName, className)}
    >
      <div
        data-slot="progress-fill"
        className={cn("h-full rounded-full bg-primary transition-[width] duration-1000 ease-out", fillClassName)}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
