"use client";

import { useQuery } from "@tanstack/react-query";
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

  if (progressQuery.isError) {
    return (
      <div className="mx-auto max-w-2xl p-4 sm:p-8">
        {backLink}
        <ErrorState
          message="Couldn't load progress."
          retryLabel="Retry"
          onRetry={() => progressQuery.refetch()}
        />
      </div>
    );
  }

  if (progressQuery.isLoading || !progressQuery.data) {
    return (
      <div className="mx-auto max-w-2xl p-4 sm:p-8" role="status" aria-label="Loading progress">
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
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      {backLink}

      <h1 className="mb-6 text-2xl font-semibold">Progress</h1>

      {!hasAnyData ? (
        <EmptyState
          icon={ChartNoAxesCombined}
          title="Nothing to show yet"
          description="Upload a document, then generate flashcards or a quiz from it — your progress will show up here."
          action={
            <Link
              href={`/subjects/${subjectId}`}
              className="text-sm text-primary hover:underline"
            >
              Go to {subjectQuery.data?.name ?? "subject"}
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
