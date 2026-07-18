"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useApiClient } from "@/lib/api/useApiClient";
import { allAnswered, scoreQuiz, type QuizAnswers } from "@/lib/quizScore";

export default function TakeQuizPage() {
  const { subjectId, quizId } = useParams<{ subjectId: string; quizId: string }>();
  const api = useApiClient();
  const [answers, setAnswers] = useState<QuizAnswers>({});
  const [revealed, setRevealed] = useState(false);

  const quizQuery = useQuery({
    queryKey: ["subjects", subjectId, "quizzes", quizId],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/quizzes/{quiz_id}", {
        params: { path: { subject_id: subjectId, quiz_id: quizId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const backLink = (
    <Link
      href={`/subjects/${subjectId}/quizzes`}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Quizzes
    </Link>
  );

  if (quizQuery.isError) {
    return (
      <div className="mx-auto max-w-2xl p-4 sm:p-8">
        {backLink}
        <p className="text-destructive">Quiz not found.</p>
      </div>
    );
  }

  if (quizQuery.isLoading || !quizQuery.data) {
    return (
      <div className="mx-auto max-w-2xl p-4 sm:p-8">
        {backLink}
        <p>Loading…</p>
      </div>
    );
  }

  const quiz = quizQuery.data;
  const questions = quiz.questions;
  const canSubmit = allAnswered(questions, answers);
  const score = revealed ? scoreQuiz(questions, answers) : null;

  const selectOption = (questionId: string, optionIndex: number) => {
    if (revealed) return; // locked once answers are revealed
    setAnswers((prev) => ({ ...prev, [questionId]: optionIndex }));
  };

  const reset = () => {
    setAnswers({});
    setRevealed(false);
  };

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      {backLink}

      <h1 className="mb-2 text-2xl font-semibold break-words">{quiz.title || "Quiz"}</h1>

      {score && (
        <p className="mb-6 text-lg font-medium" aria-live="polite">
          You scored {score.correct} / {score.total}
        </p>
      )}

      <ol className="flex flex-col gap-6">
        {questions.map((question, questionNumber) => {
          const selected = answers[question.id];
          return (
            <li key={question.id}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-medium break-words">
                    {questionNumber + 1}. {question.question}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  {question.options.map((option, optionIndex) => {
                    const isSelected = selected === optionIndex;
                    // Correctness styling is applied ONLY after reveal — before that,
                    // correct_index is never used to style anything, so the page is a
                    // real self-test, not an answer sheet.
                    const isTheCorrectOption = revealed && optionIndex === question.correct_index;
                    const isWrongPick = revealed && isSelected && !isTheCorrectOption;

                    return (
                      <button
                        key={optionIndex}
                        type="button"
                        disabled={revealed}
                        aria-pressed={isSelected}
                        onClick={() => selectOption(question.id, optionIndex)}
                        className={cn(
                          "flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors",
                          "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          !revealed && "hover:bg-muted",
                          !revealed && isSelected && "border-primary bg-primary/10",
                          isTheCorrectOption && "border-success bg-success/10 text-success",
                          isWrongPick && "border-destructive bg-destructive/10 text-destructive"
                        )}
                      >
                        <span className="min-w-0 break-words">{option}</span>
                        {isTheCorrectOption && <CheckCircle2 className="size-4 shrink-0" />}
                        {isWrongPick && <XCircle className="size-4 shrink-0" />}
                      </button>
                    );
                  })}

                  {revealed && question.explanation && (
                    <p className="mt-1 text-sm text-muted-foreground break-words">
                      {question.explanation}
                    </p>
                  )}
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>

      <div className="mt-6 flex items-center gap-3">
        {!revealed ? (
          <Button disabled={!canSubmit} onClick={() => setRevealed(true)}>
            Check answers
          </Button>
        ) : (
          <Button variant="outline" onClick={reset}>
            Try again
          </Button>
        )}
        {!revealed && !canSubmit && (
          <p className="text-sm text-muted-foreground">Answer every question to check your score.</p>
        )}
      </div>
    </div>
  );
}
