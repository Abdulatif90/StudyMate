"use client";

import { UserButton } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { useApiClient } from "@/lib/api/useApiClient";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";

export default function SubjectsPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
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
        // A 402 means the plan's subject cap is hit — capture it (status lives on the
        // response, not the body) so the UI can show an upgrade prompt instead of a
        // generic failure. Any other error falls through to the generic message.
        setLimitError(parsePlanLimitError(response.status, error));
        throw error;
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <div className="mb-8 flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Subjects</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/dashboard">Dashboard</Link>}
          />
          <UserButton />
        </div>
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>New subject</CardTitle>
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
                Name
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Biology 101"
                disabled={createSubject.isPending}
              />
            </div>
            <Button type="submit" disabled={createSubject.isPending || !name.trim()}>
              {createSubject.isPending ? "Adding…" : "Add"}
            </Button>
          </form>
          {limitError ? (
            <UpgradePrompt message={limitError.detail} />
          ) : createSubject.isError ? (
            <p className="text-destructive mt-2 text-sm">
              Couldn&apos;t create subject. Please try again.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {subjectsQuery.isLoading && <p>Loading…</p>}
      {subjectsQuery.isError && (
        <p className="text-destructive">Couldn&apos;t load subjects.</p>
      )}
      {subjectsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">No subjects yet — add one above.</p>
      )}
      <ul className="flex flex-col gap-2">
        {subjectsQuery.data?.map((subject) => (
          <li key={subject.id}>
            <Link href={`/subjects/${subject.id}`}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardContent className="py-4">
                  <p className="font-medium">{subject.name}</p>
                  <p className="text-muted-foreground text-xs">
                    Created {new Date(subject.created_at).toLocaleDateString()}
                  </p>
                </CardContent>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
