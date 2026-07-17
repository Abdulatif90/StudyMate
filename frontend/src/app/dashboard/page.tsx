"use client";

import { UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ProgressStats } from "@/components/progress-stats";
import { useApiClient } from "@/lib/api/useApiClient";

export default function DashboardPage() {
  const api = useApiClient();
  const t = useTranslations();

  const progressQuery = useQuery({
    queryKey: ["progress"],
    queryFn: async () => {
      const { data, error } = await api.GET("/progress");
      if (error) throw error;
      return data;
    },
  });

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <div className="mb-8 flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">{t("Dashboard.heading")}</h1>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/billing">{t("Nav.billing")}</Link>}
          />
          <UserButton />
        </div>
      </div>

      {progressQuery.isLoading && <p>{t("Common.loading")}</p>}
      {progressQuery.isError && (
        <p className="text-destructive">{t("Dashboard.loadError")}</p>
      )}

      {progressQuery.data && progressQuery.data.subject_count === 0 && (
        <div className="rounded-lg border border-border p-6 text-center">
          <p className="font-medium">{t("Dashboard.welcomeTitle")}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("Dashboard.welcomeBody")}
          </p>
          <Button
            className="mt-4"
            nativeButton={false}
            render={<Link href="/subjects">{t("Dashboard.getStarted")}</Link>}
          />
        </div>
      )}

      {progressQuery.data && progressQuery.data.subject_count > 0 && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {t("Dashboard.acrossSubjects", { count: progressQuery.data.subject_count })}
          </p>
          <ProgressStats
            documents={progressQuery.data.documents}
            flashcards={progressQuery.data.flashcards}
            quizCount={progressQuery.data.quiz_count}
          />
          <Link
            href="/subjects"
            className="text-sm text-primary hover:underline"
          >
            {t("Dashboard.viewAll")}
          </Link>
        </div>
      )}
    </div>
  );
}
