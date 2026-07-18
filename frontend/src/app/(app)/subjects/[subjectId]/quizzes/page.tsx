"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronRight, Trash2 } from "lucide-react";
import { useConfirm } from "@/components/confirm-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { UsageHint } from "@/components/usage-hint";
import { captureEvent } from "@/lib/analytics";
import { useApiClient } from "@/lib/api/useApiClient";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";
import { usageMeters } from "@/lib/planLimits";
import { friendlyQuizError } from "@/lib/quizError";
import { formatRelativeTime } from "@/lib/relativeTime";

const MIN_QUESTIONS = 1;
const MAX_QUESTIONS = 20;

export default function QuizzesPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const t = useTranslations();
  const locale = useLocale();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [numQuestions, setNumQuestions] = useState(5);
  const [title, setTitle] = useState("");
  const [limitError, setLimitError] = useState<PlanLimitError | null>(null);

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

  const planQuery = useQuery({
    queryKey: ["billing", "plan"],
    queryFn: async () => {
      const { data, error } = await api.GET("/billing/plan");
      if (error) throw error;
      return data;
    },
  });
  // Quiz + flashcard generation share ONE daily cap on the backend (billing.service
  // counts them together) — same meter as the flashcards page shows.
  const generationsMeter = planQuery.data
    ? usageMeters(planQuery.data).find((meter) => meter.key === "generations")
    : undefined;

  const generateQuiz = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/subjects/{subject_id}/quizzes", {
        params: { path: { subject_id: subjectId } },
        body: { num_questions: numQuestions, title: title.trim() || null, language: locale },
      });
      // 404/422/502 aren't in the generated error shape (hand-raised HTTPExceptions),
      // so map the real response.status — same pattern as the upload flow. A 402 means
      // the plan's daily generation cap is hit — captured separately so the UI can show
      // an upgrade prompt instead of the generic generate-error line.
      if (error) {
        // A 402 means the plan's daily generation cap is hit — stays inline via
        // UpgradePrompt, not a toast (FRONTEND.md §3.3); any other status toasts.
        const limit = parsePlanLimitError(response.status, error);
        setLimitError(limit);
        const message = friendlyQuizError(response.status);
        if (!limit) toast.error(t("Quizzes.generateErrorTitle"), message);
        throw new Error(message);
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "quizzes"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plan"] });
      toast.success(t("Quizzes.generateSuccess"), data.title || undefined);
      captureEvent("quizGenerated");
    },
  });

  const deleteQuiz = useMutation({
    mutationFn: async (quizId: string) => {
      const { error } = await api.DELETE("/subjects/{subject_id}/quizzes/{quiz_id}", {
        params: { path: { subject_id: subjectId, quiz_id: quizId } },
      });
      // 204 No Content on success → `data` is undefined, so `error` is what signals
      // failure here (same as the delete-document flow).
      if (error) throw new Error(t("Quizzes.deleteGenericError"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "quizzes"] });
      toast.success(t("Quizzes.deleteSuccess"));
    },
    onError: (error: Error) => {
      toast.error(t("Quizzes.deleteErrorTitle"), error.message);
    },
  });

  const backLink = (
    <Link
      href={`/subjects/${subjectId}`}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      {subjectQuery.data?.name ?? t("Common.subjectFallback")}
    </Link>
  );

  if (subjectQuery.isError) {
    return (
      <div>
        {backLink}
        <p className="text-destructive">{t("Common.subjectNotFound")}</p>
      </div>
    );
  }

  return (
    <div>
      {backLink}

      <h1 className="mb-8 text-2xl font-semibold">{t("Quizzes.heading")}</h1>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>{t("Quizzes.generateTitle")}</CardTitle>
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
              <Label htmlFor="quiz-title">{t("Quizzes.titleLabel")}</Label>
              <Input
                id="quiz-title"
                value={title}
                maxLength={200}
                placeholder={t("Quizzes.titlePlaceholder")}
                disabled={generateQuiz.isPending}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quiz-num-questions">{t("Quizzes.numQuestionsLabel")}</Label>
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
              {generateQuiz.isPending ? t("Quizzes.generating") : t("Quizzes.generate")}
            </Button>
          </form>

          {generateQuiz.isPending && (
            <p className="mt-2 text-sm text-muted-foreground">{t("Quizzes.generatingHint")}</p>
          )}
          {limitError ? (
            <UpgradePrompt message={limitError.detail} />
          ) : (
            generationsMeter && (
              <UsageHint
                meter={generationsMeter}
                text={t("Usage.generationsHint", {
                  used: generationsMeter.used,
                  cap: generationsMeter.cap ?? 0,
                })}
              />
            )
          )}
        </CardContent>
      </Card>

      {quizzesQuery.isLoading && <p>{t("Common.loading")}</p>}
      {quizzesQuery.isError && <p className="text-destructive">{t("Quizzes.loadError")}</p>}
      {quizzesQuery.data?.length === 0 && (
        <p className="text-muted-foreground">{t("Quizzes.empty")}</p>
      )}

      <ul className="flex flex-col gap-2">
        {quizzesQuery.data?.map((quiz) => (
          <li key={quiz.id}>
            <Card interactive>
              <CardContent className="flex items-center justify-between gap-3 py-4">
                <Link
                  href={`/subjects/${subjectId}/quizzes/${quiz.id}`}
                  className="group flex min-w-0 flex-1 items-center gap-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium group-hover:underline">
                      {quiz.title || t("Quizzes.untitled")}
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
                  aria-label={t("Quizzes.deleteAriaLabel", {
                    title: quiz.title || t("Quizzes.untitled"),
                  })}
                  disabled={deleteQuiz.isPending && deleteQuiz.variables === quiz.id}
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("Quizzes.deleteConfirmTitle", {
                        title: quiz.title || t("Quizzes.untitled"),
                      }),
                      description: t("Common.cantUndo"),
                      destructive: true,
                    });
                    if (!ok) return;
                    deleteQuiz.mutate(quiz.id);
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
