"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";
import { useConfirm } from "@/components/confirm-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { UsageHint } from "@/components/usage-hint";
import { useApiClient } from "@/lib/api/useApiClient";
import { friendlyFlashcardError } from "@/lib/flashcardError";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";
import { usageMeters } from "@/lib/planLimits";

const MIN_CARDS = 1;
const MAX_CARDS = 50;

export default function FlashcardsPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const t = useTranslations();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [numCards, setNumCards] = useState(10);
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

  const flashcardsQuery = useQuery({
    queryKey: ["subjects", subjectId, "flashcards"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/flashcards", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
    },
  });

  const dueQuery = useQuery({
    queryKey: ["subjects", subjectId, "flashcards", "due"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/flashcards/due", {
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
  // counts them together) — same meter as the quizzes page shows.
  const generationsMeter = planQuery.data
    ? usageMeters(planQuery.data).find((meter) => meter.key === "generations")
    : undefined;

  const generateFlashcards = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST("/subjects/{subject_id}/flashcards", {
        params: { path: { subject_id: subjectId } },
        body: { num_cards: numCards },
      });
      // 404/422/502 aren't in the generated error shape (hand-raised HTTPExceptions),
      // so map the real response.status — same pattern as the quiz generate flow. A 402
      // means the plan's daily generation cap is hit — stays inline via UpgradePrompt,
      // not a toast (FRONTEND.md §3.3); any other status toasts.
      if (error) {
        const limit = parsePlanLimitError(response.status, error);
        setLimitError(limit);
        const message = friendlyFlashcardError(response.status);
        if (!limit) toast.error(t("Flashcards.generateErrorTitle"), message);
        throw new Error(message);
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "flashcards"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plan"] });
      toast.success(t("Flashcards.generateSuccess", { count: data.length }));
    },
  });

  const deleteFlashcard = useMutation({
    mutationFn: async (flashcardId: string) => {
      const { error } = await api.DELETE("/flashcards/{flashcard_id}", {
        params: { path: { flashcard_id: flashcardId } },
      });
      // 204 No Content on success → `data` is undefined, so `error` is what signals
      // failure here (same as the delete-document/delete-quiz flows).
      if (error) throw new Error(t("Flashcards.deleteGenericError"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "flashcards"] });
      toast.success(t("Flashcards.deleteSuccess"));
    },
    onError: (error: Error) => {
      toast.error(t("Flashcards.deleteErrorTitle"), error.message);
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

  const dueCount = dueQuery.data?.length ?? 0;

  return (
    <div>
      {backLink}

      <div className="mb-8 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t("Flashcards.heading")}</h1>
        <Button
          className="shrink-0"
          disabled={dueCount === 0}
          nativeButton={false}
          render={
            <Link href={`/subjects/${subjectId}/flashcards/review`}>
              {dueCount > 0 ? t("Flashcards.reviewWithCount", { count: dueCount }) : t("Flashcards.review")}
            </Link>
          }
        />
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>{t("Flashcards.generateTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!generateFlashcards.isPending) generateFlashcards.mutate();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="flashcard-num-cards">{t("Flashcards.numCardsLabel")}</Label>
              <Input
                id="flashcard-num-cards"
                type="number"
                min={MIN_CARDS}
                max={MAX_CARDS}
                value={numCards}
                disabled={generateFlashcards.isPending}
                className="w-28"
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10);
                  if (Number.isNaN(parsed)) return;
                  setNumCards(Math.min(MAX_CARDS, Math.max(MIN_CARDS, parsed)));
                }}
              />
            </div>

            <Button type="submit" className="w-fit" disabled={generateFlashcards.isPending}>
              {generateFlashcards.isPending ? t("Flashcards.generating") : t("Flashcards.generate")}
            </Button>
          </form>

          {generateFlashcards.isPending && (
            <p className="mt-2 text-sm text-muted-foreground">{t("Flashcards.generatingHint")}</p>
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

      {flashcardsQuery.isLoading && <p>{t("Common.loading")}</p>}
      {flashcardsQuery.isError && (
        <p className="text-destructive">{t("Flashcards.loadError")}</p>
      )}
      {flashcardsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">{t("Flashcards.empty")}</p>
      )}

      <ul className="flex flex-col gap-2">
        {flashcardsQuery.data?.map((card) => (
          <li key={card.id}>
            <Card>
              <CardContent className="flex items-start justify-between gap-3 py-4">
                <div className="min-w-0 flex-1">
                  <p className="font-medium break-words">{card.front}</p>
                  <p className="mt-1 text-sm text-muted-foreground break-words">{card.back}</p>
                </div>
                <Button
                  variant="destructive"
                  size="icon-sm"
                  className="shrink-0"
                  aria-label={t("Flashcards.deleteAriaLabel", { front: card.front })}
                  disabled={deleteFlashcard.isPending && deleteFlashcard.variables === card.id}
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("Flashcards.deleteConfirmTitle"),
                      description: t("Common.cantUndo"),
                      destructive: true,
                    });
                    if (!ok) return;
                    deleteFlashcard.mutate(card.id);
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
