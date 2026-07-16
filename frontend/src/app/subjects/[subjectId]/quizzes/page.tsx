"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronRight, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiClient } from "@/lib/api/useApiClient";
import { friendlyQuizError } from "@/lib/quizError";
import { formatRelativeTime } from "@/lib/relativeTime";

const MIN_QUESTIONS = 1;
const MAX_QUESTIONS = 20;

export default function QuizzesPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [numQuestions, setNumQuestions] = useState(5);
  const [title, setTitle] = useState("");
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const subjectQuery = useQuery({
    queryKey: ["subjects", subjectId],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const quizzesQuery = useQuery({
    queryKey: ["subjects", subjectId, "quizzes"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/quizzes", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const generateQuiz = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/subjects/{subject_id}/quizzes", {
        params: { path: { subject_id: subjectId } },
        body: { num_questions: numQuestions, title: title.trim() || null },
      });
      // 404/422/502 aren't in the generated error shape (hand-raised HTTPExceptions),
      // so map the real response.status — same pattern as the upload flow.
      if (error) throw new Error(friendlyQuizError(response.status));
      return data;
    },
    onSuccess: () => {
      setGenerateError(null);
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "quizzes"] });
    },
    onError: (error: Error) => {
      setGenerateError(error.message);
    },
  });

  const deleteQuiz = useMutation({
    mutationFn: async (quizId: string) => {
      const { error } = await api.DELETE("/subjects/{subject_id}/quizzes/{quiz_id}", {
        params: { path: { subject_id: subjectId, quiz_id: quizId } },
      });
      // 204 No Content on success → `data` is undefined, so `error` is what signals
      // failure here (same as the delete-document flow).
      if (error) throw new Error("Couldn't delete this quiz. Please try again.");
    },
    onSuccess: () => {
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "quizzes"] });
    },
    onError: (error: Error) => {
      setDeleteError(error.message);
    },
  });

  const backLink = (
    <Link
      href={`/subjects/${subjectId}`}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      {subjectQuery.data?.name ?? "Subject"}
    </Link>
  );

  if (subjectQuery.isError) {
    return (
      <div className="mx-auto max-w-2xl p-4 sm:p-8">
        {backLink}
        <p className="text-destructive">Subject not found.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      {backLink}

      <h1 className="mb-8 text-2xl font-semibold">Quizzes</h1>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Generate a quiz</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!generateQuiz.isPending) generateQuiz.mutate();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quiz-title">Title (optional)</Label>
              <Input
                id="quiz-title"
                value={title}
                maxLength={200}
                placeholder="e.g. Chapter 3 review"
                disabled={generateQuiz.isPending}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quiz-num-questions">Number of questions</Label>
              <Input
                id="quiz-num-questions"
                type="number"
                min={MIN_QUESTIONS}
                max={MAX_QUESTIONS}
                value={numQuestions}
                disabled={generateQuiz.isPending}
                className="w-28"
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10);
                  if (Number.isNaN(parsed)) return;
                  setNumQuestions(Math.min(MAX_QUESTIONS, Math.max(MIN_QUESTIONS, parsed)));
                }}
              />
            </div>

            <Button type="submit" className="w-fit" disabled={generateQuiz.isPending}>
              {generateQuiz.isPending ? "Generating…" : "Generate quiz"}
            </Button>
          </form>

          {generateQuiz.isPending && (
            <p className="mt-2 text-sm text-muted-foreground">
              Generating questions from your material — this can take a few seconds.
            </p>
          )}
          {generateError && <p className="mt-2 text-sm text-destructive">{generateError}</p>}
        </CardContent>
      </Card>

      {quizzesQuery.isLoading && <p>Loading…</p>}
      {quizzesQuery.isError && <p className="text-destructive">Couldn&apos;t load quizzes.</p>}
      {quizzesQuery.data?.length === 0 && (
        <p className="text-muted-foreground">No quizzes yet — generate one above.</p>
      )}
      {deleteError && <p className="mb-2 text-sm text-destructive">{deleteError}</p>}

      <ul className="flex flex-col gap-2">
        {quizzesQuery.data?.map((quiz) => (
          <li key={quiz.id}>
            <Card>
              <CardContent className="flex items-center justify-between gap-3 py-4">
                <Link
                  href={`/subjects/${subjectId}/quizzes/${quiz.id}`}
                  className="group flex min-w-0 flex-1 items-center gap-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium group-hover:underline">
                      {quiz.title || "Untitled quiz"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatRelativeTime(quiz.created_at)}
                    </p>
                  </div>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                </Link>
                <Button
                  variant="destructive"
                  size="icon-sm"
                  className="shrink-0"
                  aria-label={`Delete ${quiz.title || "quiz"}`}
                  disabled={deleteQuiz.isPending && deleteQuiz.variables === quiz.id}
                  onClick={() => {
                    if (window.confirm(`Delete "${quiz.title || "this quiz"}"? This can't be undone.`)) {
                      deleteQuiz.mutate(quiz.id);
                    }
                  }}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
