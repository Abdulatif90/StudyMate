"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiClient } from "@/lib/api/useApiClient";
import { GRADE_BUTTONS, isLapseGrade } from "@/lib/gradeButtons";
import { reviewProgress } from "@/lib/reviewProgress";
import type { components } from "@/lib/api/schema";

type FlashcardRead = components["schemas"]["FlashcardRead"];

export default function ReviewFlashcardsPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const t = useTranslations();
  const api = useApiClient();
  const queryClient = useQueryClient();

  // Snapshot the due list ONCE at session start and step through that fixed array by
  // index — the session must not reshuffle mid-review just because a background
  // refetch of /due drops the card that was just graded (see reviewProgress.ts).
  const [sessionCards, setSessionCards] = useState<FlashcardRead[] | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

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

  useEffect(() => {
    if (sessionCards === null && dueQuery.data) {
      setSessionCards(dueQuery.data);
    }
  }, [sessionCards, dueQuery.data]);

  const reviewCard = useMutation({
    mutationFn: async ({ flashcardId, grade }: { flashcardId: string; grade: number }) => {
      const { error } = await api.POST("/flashcards/{flashcard_id}/review", {
        params: { path: { flashcard_id: flashcardId } },
        body: { grade },
      });
      if (error) throw new Error(t("FlashcardReview.reviewError"));
    },
    onSuccess: () => {
      setReviewError(null);
      setRevealed(false);
      setCurrentIndex((index) => index + 1);
      // Refresh the list/due-count queries the flashcards page reads — the session's
      // own local `sessionCards` array stays fixed so stepping through it doesn't jump.
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "flashcards"] });
    },
    onError: (error: Error) => {
      setReviewError(error.message);
    },
  });

  const backLink = (
    <Link
      href={`/subjects/${subjectId}/flashcards`}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      {t("Flashcards.heading")}
    </Link>
  );

  if (dueQuery.isError) {
    return (
      <div>
        {backLink}
        <p className="text-destructive">{t("FlashcardReview.loadError")}</p>
      </div>
    );
  }

  if (dueQuery.isLoading || sessionCards === null) {
    return (
      <div>
        {backLink}
        <p>{t("Common.loading")}</p>
      </div>
    );
  }

  const progress = reviewProgress(sessionCards.length, currentIndex);

  if (progress.isComplete) {
    return (
      <div>
        {backLink}
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-10 text-center">
            <p className="text-lg font-medium">
              {sessionCards.length === 0 ? t("FlashcardReview.noneDue") : t("FlashcardReview.doneForNow")}
            </p>
            <p className="text-sm text-muted-foreground">
              {sessionCards.length === 0
                ? t("FlashcardReview.comeBackLater")
                : t("FlashcardReview.reviewedCount", { count: sessionCards.length })}
            </p>
            <Button
              className="mt-4"
              nativeButton={false}
              render={
                <Link href={`/subjects/${subjectId}/flashcards`}>
                  {t("FlashcardReview.backToFlashcards")}
                </Link>
              }
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  const card = sessionCards[currentIndex];

  return (
    <div>
      {backLink}

      <p className="mb-4 text-sm text-muted-foreground" aria-live="polite">
        {t("FlashcardReview.cardProgress", { current: progress.current, total: progress.total })}
      </p>

      <Card className="mb-6">
        <CardContent className="flex min-h-40 flex-col justify-center gap-4 py-8 text-center">
          <p className="text-lg font-medium break-words">{card.front}</p>
          {revealed && (
            <p className="border-t border-border pt-4 text-base break-words text-muted-foreground">
              {card.back}
            </p>
          )}
        </CardContent>
      </Card>

      {reviewError && <p className="mb-4 text-sm text-destructive">{reviewError}</p>}

      {!revealed ? (
        <Button className="w-full sm:w-auto" onClick={() => setRevealed(true)}>
          {t("FlashcardReview.showAnswer")}
        </Button>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          {GRADE_BUTTONS.map((button) => (
            <Button
              key={button.key}
              variant={isLapseGrade(button.grade) ? "destructive" : "outline"}
              disabled={reviewCard.isPending}
              className={
                button.key === "easy" ? "border-success text-success hover:bg-success/10" : ""
              }
              onClick={() => {
                if (!reviewCard.isPending) {
                  reviewCard.mutate({ flashcardId: card.id, grade: button.grade });
                }
              }}
            >
              {t(`FlashcardReview.grade.${button.key}`)}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
