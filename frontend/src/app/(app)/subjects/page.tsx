"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useConfirm } from "@/components/confirm-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { useApiClient } from "@/lib/api/useApiClient";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";

export default function SubjectsPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  // The confirm/toast strings on this page are deliberately plain English, not run
  // through next-intl's `t()` — this increment (FRONTEND.md §3) is scoped to closing
  // interaction gaps, not extending i18n coverage. The rest of this page's existing
  // copy stays translated; converting these new strings is tracked separately in
  // docs/PROGRESS.md's i18n follow-ups.
  const t = useTranslations();
  const [name, setName] = useState("");
  const [limitError, setLimitError] = useState<PlanLimitError | null>(null);

  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects");
      if (error) throw error;
      return data;
    },
  });

  const createSubject = useMutation({
    mutationFn: async (newName: string) => {
      const { data, error, response } = await api.POST("/subjects", {
        body: { name: newName },
      });
      if (error) {
        // A 402 means the plan's subject cap is hit — stays inline via UpgradePrompt,
        // not a toast (FRONTEND.md §3.3); any other error toasts a generic failure.
        const limit = parsePlanLimitError(response.status, error);
        setLimitError(limit);
        if (!limit) toast.error("Couldn't create subject", "Please try again.");
        throw error;
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["subjects"] });
      toast.success("Subject created", data.name);
    },
  });

  const deleteSubject = useMutation({
    mutationFn: async (subjectId: string) => {
      const { error, response } = await api.DELETE("/subjects/{subject_id}", {
        params: { path: { subject_id: subjectId } },
      });
      // 204 No Content on success — `data` is undefined, so `error` is what actually
      // signals failure here (same as the document/quiz/flashcard delete flows).
      if (error) {
        throw new Error(
          response.status === 404
            ? "This subject was already deleted or couldn't be found."
            : "Couldn't delete this subject. Please try again.",
        );
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subjects"] });
      toast.success("Subject deleted");
    },
    onError: (error: Error) => {
      toast.error("Couldn't delete subject", error.message);
    },
  });

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <h1 className="mb-8 text-2xl font-semibold">{t("Subjects.heading")}</h1>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>{t("Subjects.newSubject")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (name.trim()) createSubject.mutate(name.trim());
            }}
          >
            <div className="flex-1">
              <Label htmlFor="name" className="sr-only">
                {t("Subjects.nameLabel")}
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("Subjects.namePlaceholder")}
                disabled={createSubject.isPending}
              />
            </div>
            <Button type="submit" disabled={createSubject.isPending || !name.trim()}>
              {createSubject.isPending ? t("Subjects.adding") : t("Subjects.add")}
            </Button>
          </form>
          {limitError && <UpgradePrompt message={limitError.detail} />}
        </CardContent>
      </Card>

      {subjectsQuery.isLoading && <p>{t("Common.loading")}</p>}
      {subjectsQuery.isError && (
        <p className="text-destructive">{t("Subjects.loadError")}</p>
      )}
      {subjectsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">{t("Subjects.empty")}</p>
      )}
      <ul className="flex flex-col gap-2">
        {subjectsQuery.data?.map((subject) => (
          <li key={subject.id}>
            <Card>
              <CardContent className="flex items-center justify-between gap-3 py-4">
                {/* The delete button below must be a SIBLING of this Link, not nested
                    inside it — nesting would make a delete click also navigate. */}
                <Link href={`/subjects/${subject.id}`} className="group min-w-0 flex-1">
                  <p className="font-medium group-hover:underline">{subject.name}</p>
                  <p className="text-muted-foreground text-xs">
                    {t("Subjects.createdOn", {
                      date: new Date(subject.created_at).toLocaleDateString(),
                    })}
                  </p>
                </Link>
                <Button
                  variant="destructive"
                  size="icon-sm"
                  className="shrink-0"
                  aria-label={`Delete ${subject.name}`}
                  disabled={deleteSubject.isPending && deleteSubject.variables === subject.id}
                  onClick={async () => {
                    // Copy deliberately does NOT claim this cascades to the subject's
                    // documents/quizzes/flashcards — the backend has no ON DELETE
                    // CASCADE on any of those FKs (checked the migrations), so deleting
                    // a subject that still has content will error rather than clean up
                    // after itself. That's a backend gap, flagged in docs/PROGRESS.md;
                    // out of scope to fix in this frontend-only increment.
                    const ok = await confirm({
                      title: `Delete "${subject.name}"?`,
                      description: "This can't be undone.",
                      destructive: true,
                    });
                    if (!ok) return;
                    deleteSubject.mutate(subject.id);
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
