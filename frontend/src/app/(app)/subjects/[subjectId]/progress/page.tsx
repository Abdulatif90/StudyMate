"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ChartNoAxesCombined } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { ProgressStats } from "@/components/progress-stats";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiClient } from "@/lib/api/useApiClient";

export default function SubjectProgressPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const t = useTranslations();
  const api = useApiClient();

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

  const progressQuery = useQuery({
    queryKey: ["subjects", subjectId, "progress"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/progress", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
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

  if (progressQuery.isError) {
    return (
      <div>
        {backLink}
        <ErrorState
          message={t("Progress.loadError")}
          retryLabel={t("Common.retry")}
          onRetry={() => progressQuery.refetch()}
        />
      </div>
    );
  }

  if (progressQuery.isLoading || !progressQuery.data) {
    return (
      <div role="status" aria-label={t("Progress.loadingAriaLabel")}>
        {backLink}
        <Skeleton className="mb-6 h-8 w-32" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  const progress = progressQuery.data;
  const hasAnyData =
    progress.documents.total > 0 || progress.flashcards.total > 0 || progress.quiz_count > 0;

  return (
    <div>
      {backLink}

      <h1 className="mb-6 text-2xl font-semibold">{t("Progress.heading")}</h1>

      {!hasAnyData ? (
        <EmptyState
          icon={ChartNoAxesCombined}
          title={t("Progress.emptyTitle")}
          description={t("Progress.emptyDescription")}
          action={
            <Link
              href={`/subjects/${subjectId}`}
              className="text-sm text-primary hover:underline"
            >
              {t("Progress.goToSubject", {
                name: subjectQuery.data?.name ?? t("Common.subjectFallback"),
              })}
            </Link>
          }
        />
      ) : (
        <ProgressStats
          documents={progress.documents}
          flashcards={progress.flashcards}
          quizCount={progress.quiz_count}
        />
      )}
    </div>
  );
}
