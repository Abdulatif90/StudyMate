// Pure grading logic for a taken quiz — no React, no correct_index revealed until the
// caller decides to (this only computes; the page holds the reveal state). `answers`
// maps a question id to the index of the option the user picked.

export type QuizAnswers = Record<string, number>;

interface GradableQuestion {
  id: string;
  correct_index: number;
}

/** True once every question has a selected answer — gates the "Check answers" button
 * so a quiz can't be submitted half-finished. */
export function allAnswered(questions: GradableQuestion[], answers: QuizAnswers): boolean {
  return questions.length > 0 && questions.every((q) => answers[q.id] !== undefined);
}

/** Whether the answer picked for `question` is the correct one. Unanswered → false. */
export function isCorrect(question: GradableQuestion, answers: QuizAnswers): boolean {
  return answers[question.id] === question.correct_index;
}

/** How many questions were answered correctly, out of the total. */
export function scoreQuiz(
  questions: GradableQuestion[],
  answers: QuizAnswers
): { correct: number; total: number } {
  const correct = questions.reduce((count, q) => count + (isCorrect(q, answers) ? 1 : 0), 0);
  return { correct, total: questions.length };
}

export interface QuizAttemptRequestBody {
  answers: QuizAnswers;
}

/**
 * Builds the POST body for persisting a graded attempt (`.../quizzes/{quizId}/attempts`).
 * The server re-grades from `answers` itself — a client-computed score is never sent, so
 * this is a thin, explicit wire boundary between the client-side self-test (`scoreQuiz`)
 * and the persisted attempt, kept separate so the two can evolve independently.
 */
export function toAttemptRequestBody(answers: QuizAnswers): QuizAttemptRequestBody {
  return { answers };
}
