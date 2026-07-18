"use client";

import { useUser } from "@clerk/nextjs";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import {
  BookOpen,
  ChevronRight,
  Circle,
  CircleCheck,
  FileText,
  Layers,
  ListChecks,
  Plus,
} from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageMeters } from "@/components/usage-meters";
import { useApiClient } from "@/lib/api/useApiClient";
import { onboardingSteps } from "@/lib/onboardingChecklist";
import { subjectCardStats } from "@/lib/subjectCardStats";
import type { components } from "@/lib/api/schema";

type SubjectProgress = components["schemas"]["SubjectProgress"];

// A dashboard preview, not the management page — cap how many subject cards show here
// and point to /subjects for the rest, rather than growing this hub unbounded for a
// Pro/Business account with many subjects.
const SUBJECT_PREVIEW_LIMIT = 6;

const STEP_ICON = { done: CircleCheck, pending: Circle } as const;

function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8" role="status" aria-label="Loading dashboard">
      <Skeleton className="mb-2 h-8 w-56" />
      <Skeleton className="mb-8 h-4 w-40" />
      <Skeleton className="mb-6 h-32 w-full rounded-xl" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const api = useApiClient();
  const t = useTranslations();
  const { user } = useUser();

  const progressQuery = useQuery({
    queryKey: ["progress"],
    queryFn: async () => {
      const { data, error } = await api.GET("/progress");
      if (error) throw error;
      return data;
    },
  });

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

  const subjects = subjectsQuery.data ?? [];
  const previewSubjects = subjects.slice(0, SUBJECT_PREVIEW_LIMIT);

  // One progress fetch per previewed subject, in parallel — same `useQueries` pattern
  // already used on the Ask page's conversation-preview sidebar. Bounded by the
  // preview limit above, not the account's full subject count.
  const subjectProgressQueries = useQueries({
    queries: previewSubjects.map((subject) => ({
      queryKey: ["subjects", subject.id, "progress"],
      queryFn: async (): Promise<SubjectProgress> => {
        const { data, error } = await api.GET("/subjects/{subject_id}/progress", {
          params: { path: { subject_id: subject.id } },
        });
        if (error) throw error;
        return data;
      },
    })),
  });

  const progressBySubjectId = new Map<string, SubjectProgress | undefined>(
    previewSubjects.map((subject, index) => [subject.id, subjectProgressQueries[index]?.data])
  );

  if (progressQuery.isLoading || subjectsQuery.isLoading) {
    return <DashboardSkeleton />;
  }

  if (progressQuery.isError || subjectsQuery.isError) {
    return (
      <div className="mx-auto max-w-5xl p-4 sm:p-8">
        <ErrorState
          message={t("Dashboard.loadError")}
          retryLabel={t("Common.retry")}
          onRetry={() => {
            progressQuery.refetch();
            subjectsQuery.refetch();
          }}
        />
      </div>
    );
  }

  const progress = progressQuery.data;
  if (!progress) return null;

  const steps = onboardingSteps(progress);
  const allStepsDone = steps.every((step) => step.done);
  const firstName = user?.firstName;

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <h1 className="mb-8 text-2xl font-semibold">
        {firstName ? t("Dashboard.greetingNamed", { name: firstName }) : t("Dashboard.greeting")}
      </h1>

      {!allStepsDone && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="text-base">{t("Dashboard.checklistTitle")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {steps.map((step) => {
                const Icon = STEP_ICON[step.done ? "done" : "pending"];
                return (
                  <li key={step.key} className="flex items-center gap-2 text-sm">
                    <Icon
                      aria-hidden
                      className={
                        step.done ? "size-4 shrink-0 text-success" : "size-4 shrink-0 text-muted-foreground"
                      }
                    />
                    <span className={step.done ? "text-muted-foreground line-through" : "text-foreground"}>
                      {t(`Dashboard.checklistStep.${step.key}`)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      {progress.subject_count === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={t("Dashboard.welcomeTitle")}
          description={t("Dashboard.welcomeBody")}
          action={
            <Button
              nativeButton={false}
              render={
                <Link href="/subjects">
                  <Plus className="size-4" aria-hidden />
                  {t("Dashboard.getStarted")}
                </Link>
              }
            />
          }
        />
      ) : (
        <div className="flex flex-col gap-6">
          {planQuery.data && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between gap-2 text-base">
                  <span>{t("Dashboard.planCardTitle")}</span>
                  <Link href="/billing" className="text-sm font-normal text-primary hover:underline">
                    {t("Dashboard.managePlan")}
                  </Link>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <UsageMeters plan={planQuery.data} />
              </CardContent>
            </Card>
          )}

          <div className="flex items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">
              {t("Dashboard.acrossSubjects", { count: progress.subject_count })}
            </p>
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={
                <Link href="/subjects">
                  <Plus className="size-4" aria-hidden />
                  {t("Dashboard.newSubject")}
                </Link>
              }
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {previewSubjects.map((subject) => {
              const subjectProgress = progressBySubjectId.get(subject.id);
              const stats = subjectProgress ? subjectCardStats(subjectProgress) : null;
              return (
                <Link key={subject.id} href={`/subjects/${subject.id}`} className="block">
                  <Card interactive className="h-full">
                    <CardContent className="flex h-full flex-col justify-between gap-3 py-4">
                      <div className="flex items-center justify-between gap-2">
                        <p className="min-w-0 truncate font-medium">{subject.name}</p>
                        <ChevronRight
                          aria-hidden
                          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover/card:translate-x-0.5"
                        />
                      </div>
                      {stats ? (
                        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                          <span className="inline-flex items-center gap-1">
                            <FileText className="size-3.5" aria-hidden />
                            {t("Dashboard.statDocuments", { count: stats[0].value })}
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <Layers className="size-3.5" aria-hidden />
                            {t("Dashboard.statFlashcardsDue", { count: stats[1].value })}
                          </span>
                          <span className="inline-flex items-center gap-1">
                            <ListChecks className="size-3.5" aria-hidden />
                            {t("Dashboard.statQuizzes", { count: stats[2].value })}
                          </span>
                        </div>
                      ) : (
                        <div className="flex gap-3">
                          <Skeleton className="h-4 w-16" />
                          <Skeleton className="h-4 w-16" />
                          <Skeleton className="h-4 w-16" />
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>

          {subjects.length > SUBJECT_PREVIEW_LIMIT && (
            <Link href="/subjects" className="text-sm text-primary hover:underline">
              {t("Dashboard.viewAllCount", { count: subjects.length })}
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
