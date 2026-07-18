"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { BookOpen, Trash2 } from "lucide-react";
import { useConfirm } from "@/components/confirm-provider";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { UsageHint } from "@/components/usage-hint";
import { useApiClient } from "@/lib/api/useApiClient";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";
import { usageMeters } from "@/lib/planLimits";

export default function SubjectsPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
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

  const planQuery = useQuery({
    queryKey: ["billing", "plan"],
    queryFn: async () => {
      const { data, error } = await api.GET("/billing/plan");
      if (error) throw error;
      return data;
    },
  });
  const subjectsMeter = planQuery.data
    ? usageMeters(planQuery.data).find((meter) => meter.key === "subjects")
    : undefined;

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
        if (!limit) toast.error(t("Subjects.createErrorTitle"), t("Common.tryAgain"));
        throw error;
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["subjects"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plan"] });
      toast.success(t("Subjects.createSuccess"), data.name);
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
          response.status === 404 ? t("Subjects.deleteNotFound") : t("Subjects.deleteGenericError"),
        );
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subjects"] });
      queryClient.invalidateQueries({ queryKey: ["billing", "plan"] });
      toast.success(t("Subjects.deleteSuccess"));
    },
    onError: (error: Error) => {
      toast.error(t("Subjects.deleteErrorTitle"), error.message);
    },
  });

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
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
          {limitError ? (
            <UpgradePrompt message={limitError.detail} />
          ) : (
            subjectsMeter && (
              <UsageHint
                meter={subjectsMeter}
                text={t("Subjects.usageHint", {
                  used: subjectsMeter.used,
                  cap: subjectsMeter.cap ?? 0,
                })}
              />
            )
          )}
        </CardContent>
      </Card>

      {subjectsQuery.isLoading && (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          role="status"
          aria-label={t("Common.loading")}
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}
      {subjectsQuery.isError && (
        <ErrorState
          message={t("Subjects.loadError")}
          retryLabel={t("Common.retry")}
          onRetry={() => subjectsQuery.refetch()}
        />
      )}
      {subjectsQuery.data?.length === 0 && (
        <EmptyState icon={BookOpen} title={t("Subjects.empty")} />
      )}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {subjectsQuery.data?.map((subject) => (
          <li key={subject.id}>
            <Card interactive>
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
                  aria-label={t("Subjects.deleteAriaLabel", { name: subject.name })}
                  disabled={deleteSubject.isPending && deleteSubject.variables === subject.id}
                  onClick={async () => {
                    // Deleting a subject cascades to its documents (+ R2 objects),
                    // quizzes, flashcards, and conversations on the backend
                    // (subjects.service.delete_subject) — so the copy below is
                    // deliberately plain ("can't be undone"), not a claim about what
                    // gets removed, since the exact scope isn't this dialog's job to
                    // enumerate.
                    const ok = await confirm({
                      title: t("Subjects.deleteConfirmTitle", { name: subject.name }),
                      description: t("Subjects.deleteConfirmDescription"),
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
