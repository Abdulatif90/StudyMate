"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { useApiClient } from "@/lib/api/useApiClient";
import { friendlyFlashcardError } from "@/lib/flashcardError";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";

const MIN_CARDS = 1;
const MAX_CARDS = 50;

export default function FlashcardsPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
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
        if (!limit) toast.error("Couldn't generate flashcards", message);
        throw new Error(message);
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "flashcards"] });
      toast.success(`${data.length} flashcard${data.length === 1 ? "" : "s"} generated`);
    },
  });

  const deleteFlashcard = useMutation({
    mutationFn: async (flashcardId: string) => {
      const { error } = await api.DELETE("/flashcards/{flashcard_id}", {
        params: { path: { flashcard_id: flashcardId } },
      });
      // 204 No Content on success → `data` is undefined, so `error` is what signals
      // failure here (same as the delete-document/delete-quiz flows).
      if (error) throw new Error("Couldn't delete this flashcard. Please try again.");
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "flashcards"] });
      toast.success("Flashcard deleted");
    },
    onError: (error: Error) => {
      toast.error("Couldn't delete flashcard", error.message);
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

  const dueCount = dueQuery.data?.length ?? 0;

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      {backLink}

      <div className="mb-8 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Flashcards</h1>
        <Button
          className="shrink-0"
          disabled={dueCount === 0}
          nativeButton={false}
          render={<Link href={`/subjects/${subjectId}/flashcards/review`}>Review{dueCount > 0 ? ` (${dueCount})` : ""}</Link>}
        />
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Generate flashcards</CardTitle>
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
              <Label htmlFor="flashcard-num-cards">Number of cards</Label>
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
              {generateFlashcards.isPending ? "Generating…" : "Generate flashcards"}
            </Button>
          </form>

          {generateFlashcards.isPending && (
            <p className="mt-2 text-sm text-muted-foreground">
              Generating cards from your material — this can take a few seconds.
            </p>
          )}
          {limitError && <UpgradePrompt message={limitError.detail} />}
        </CardContent>
      </Card>

      {flashcardsQuery.isLoading && <p>Loading…</p>}
      {flashcardsQuery.isError && (
        <p className="text-destructive">Couldn&apos;t load flashcards.</p>
      )}
      {flashcardsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">No flashcards yet — generate some above.</p>
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
                  aria-label={`Delete flashcard "${card.front}"`}
                  disabled={deleteFlashcard.isPending && deleteFlashcard.variables === card.id}
                  onClick={async () => {
                    const ok = await confirm({
                      title: "Delete this flashcard?",
                      description: "This can't be undone.",
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
