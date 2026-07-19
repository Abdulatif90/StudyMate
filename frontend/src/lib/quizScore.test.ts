import { describe, expect, it } from "vitest";
import {
  allAnswered,
  isCorrect,
  scoreQuiz,
  toAttemptRequestBody,
  type QuizAnswers,
} from "./quizScore";

const questions = [
  { id: "a", correct_index: 1 },
  { id: "b", correct_index: 0 },
  { id: "c", correct_index: 2 },
];

describe("allAnswered", () => {
  it("is false until every question has an answer", () => {
    expect(allAnswered(questions, { a: 1, b: 0 })).toBe(false);
  });

  it("is true once all questions are answered", () => {
    expect(allAnswered(questions, { a: 1, b: 0, c: 2 })).toBe(true);
  });

  it("treats a selected index of 0 as answered (not missing)", () => {
    expect(allAnswered([{ id: "b", correct_index: 0 }], { b: 0 })).toBe(true);
  });

  it("is false for an empty quiz", () => {
    expect(allAnswered([], {})).toBe(false);
  });
});

describe("isCorrect", () => {
  it("is true when the picked index matches correct_index", () => {
    expect(isCorrect({ id: "a", correct_index: 1 }, { a: 1 })).toBe(true);
  });

  it("is false for a wrong pick", () => {
    expect(isCorrect({ id: "a", correct_index: 1 }, { a: 0 })).toBe(false);
  });

  it("is false when unanswered", () => {
    expect(isCorrect({ id: "a", correct_index: 1 }, {})).toBe(false);
  });
});

describe("scoreQuiz", () => {
  it("counts correct answers out of the total", () => {
    const answers: QuizAnswers = { a: 1, b: 1, c: 2 }; // a right, b wrong, c right
    expect(scoreQuiz(questions, answers)).toEqual({ correct: 2, total: 3 });
  });

  it("scores a perfect quiz", () => {
    expect(scoreQuiz(questions, { a: 1, b: 0, c: 2 })).toEqual({ correct: 3, total: 3 });
  });

  it("scores zero when all wrong", () => {
    expect(scoreQuiz(questions, { a: 0, b: 1, c: 0 })).toEqual({ correct: 0, total: 3 });
  });

  it("counts unanswered questions as incorrect", () => {
    expect(scoreQuiz(questions, { a: 1 })).toEqual({ correct: 1, total: 3 });
  });
});

describe("toAttemptRequestBody", () => {
  it("wraps the answers map under an 'answers' key", () => {
    const answers: QuizAnswers = { a: 1, b: 0 };
    expect(toAttemptRequestBody(answers)).toEqual({ answers: { a: 1, b: 0 } });
  });

  it("wraps an empty answers map unchanged", () => {
    expect(toAttemptRequestBody({})).toEqual({ answers: {} });
  });
});
