"use client";

import { UserButton } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LanguageSwitcher } from "@/components/language-switcher";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { useApiClient } from "@/lib/api/useApiClient";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";

export default function SubjectsPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
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
        <h1 className="text-2xl font-semibold">{t("Subjects.heading")}</h1>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/dashboard">{t("Nav.dashboard")}</Link>}
          />
          <UserButton />
        </div>
      </div>

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
          ) : createSubject.isError ? (
            <p className="text-destructive mt-2 text-sm">{t("Subjects.createError")}</p>
          ) : null}
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
            <Link href={`/subjects/${subject.id}`}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardContent className="py-4">
                  <p className="font-medium">{subject.name}</p>
                  <p className="text-muted-foreground text-xs">
                    {t("Subjects.createdOn", {
                      date: new Date(subject.created_at).toLocaleDateString(),
                    })}
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
