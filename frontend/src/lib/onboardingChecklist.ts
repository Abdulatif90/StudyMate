import type { components } from "@/lib/api/schema";

type OverallProgress = components["schemas"]["OverallProgress"];

export interface ChecklistStep {
  key: "createSubject" | "uploadDocument" | "tryGeneration";
  done: boolean;
}

/** Derives the 3-step "getting started" checklist purely from existing `GET /progress`
 * data — no new tracking needed. `tryGeneration` counts EITHER a quiz or a flashcard as
 * "tried", since a student might reach for either one first. */
export function onboardingSteps(progress: OverallProgress): ChecklistStep[] {
  return [
    { key: "createSubject", done: progress.subject_count > 0 },
    { key: "uploadDocument", done: progress.documents.total > 0 },
    { key: "tryGeneration", done: progress.quiz_count > 0 || progress.flashcards.total > 0 },
  ];
}
