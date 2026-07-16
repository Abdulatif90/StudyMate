import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's automatic cleanup relies on a global `afterEach`,
// which only exists if vitest's `test.globals` is enabled — it isn't here (test
// files import { describe, it, expect } explicitly instead), so it's wired up
// manually: without this, renders from earlier tests in the same file stick
// around in the DOM and cause "multiple elements found" failures in later tests.
afterEach(() => {
  cleanup();
});
