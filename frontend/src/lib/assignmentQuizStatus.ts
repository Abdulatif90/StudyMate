/**
 * Decides how a student's assignment card should render its completion state.
 *
 * An assignment linked to a quiz (`quiz_id != null`) never shows a manual score entry —
 * its submission, if any, was auto-created server-side when the student posted a graded
 * attempt to `.../quizzes/{quizId}/attempts` (Phase 5 increment 4a), so the score is
 * real, not self-reported. An assignment with no linked quiz is a plain done/not-done
 * toggle with no score at all.
 */

export type AssignmentQuizStatus =
  | { kind: "quiz-not-started" }
  | { kind: "quiz-completed"; score: number | null }
  | { kind: "manual-not-done" }
  | { kind: "manual-done" };

interface MinimalSubmission {
  score?: number | null;
}

export function assignmentQuizStatus(
  quizId: string | null | undefined,
  submission: MinimalSubmission | null | undefined,
): AssignmentQuizStatus {
  const isSubmitted = submission != null;

  if (quizId != null) {
    return isSubmitted
      ? { kind: "quiz-completed", score: submission.score ?? null }
      : { kind: "quiz-not-started" };
  }
  return isSubmitted ? { kind: "manual-done" } : { kind: "manual-not-done" };
}
