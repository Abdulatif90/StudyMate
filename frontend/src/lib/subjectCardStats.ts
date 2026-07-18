import type { components } from "@/lib/api/schema";

type SubjectProgress = components["schemas"]["SubjectProgress"];

export interface SubjectCardStat {
  key: "documents" | "flashcardsDue" | "quizzes";
  value: number;
}

/** The at-a-glance numbers shown on a dashboard subject card: total documents,
 * flashcards currently due for review (the actionable number, not the full deck size),
 * and quizzes generated. Each caller pairs these with its own translated label. */
export function subjectCardStats(progress: SubjectProgress): SubjectCardStat[] {
  return [
    { key: "documents", value: progress.documents.total },
    { key: "flashcardsDue", value: progress.flashcards.due },
    { key: "quizzes", value: progress.quiz_count },
  ];
}
