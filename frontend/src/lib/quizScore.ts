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
