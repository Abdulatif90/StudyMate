"use client";

import { UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ProgressStats } from "@/components/progress-stats";
import { useApiClient } from "@/lib/api/useApiClient";

export default function DashboardPage() {
  const api = useApiClient();

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
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/billing">Plan &amp; billing</Link>}
          />
          <UserButton />
        </div>
      </div>

      {progressQuery.isLoading && <p>Loading…</p>}
      {progressQuery.isError && (
        <p className="text-destructive">Couldn&apos;t load progress.</p>
      )}

      {progressQuery.data && progressQuery.data.subject_count === 0 && (
        <div className="rounded-lg border border-border p-6 text-center">
          <p className="font-medium">Welcome to StudyMate</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create a subject and upload a document to get started — your study
            progress will show up here.
          </p>
          <Button
            className="mt-4"
            nativeButton={false}
            render={<Link href="/subjects">Get started</Link>}
          />
        </div>
      )}

      {progressQuery.data && progressQuery.data.subject_count > 0 && (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Across {progressQuery.data.subject_count}{" "}
            {progressQuery.data.subject_count === 1 ? "subject" : "subjects"}
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
            View all subjects
          </Link>
        </div>
      )}
    </div>
  );
}
