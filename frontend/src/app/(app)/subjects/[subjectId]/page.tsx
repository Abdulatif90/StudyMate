"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import { UpgradePrompt } from "@/components/upgrade-prompt";
import { useConfirm } from "@/components/confirm-provider";
import { useApiClient } from "@/lib/api/useApiClient";
import { friendlyDeleteError } from "@/lib/deleteError";
import { documentStatusVariant } from "@/lib/documentStatus";
import { documentsRefetchInterval } from "@/lib/documentsPolling";
import { parsePlanLimitError, type PlanLimitError } from "@/lib/planLimitError";
import { friendlyUploadError } from "@/lib/uploadError";

export default function SubjectDetailPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const t = useTranslations();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const documentsQuery = useQuery({
    queryKey: ["subjects", subjectId, "documents"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/documents", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
    },
    // Processing is async (Inngest) — a just-uploaded document sits on `pending`
    // until the job resolves it, so poll while any are pending, then stop.
    refetchInterval: (query) => documentsRefetchInterval(query.state.data),
  });

  const uploadDocument = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const { data, error, response } = await api.POST("/subjects/{subject_id}/documents", {
        params: { path: { subject_id: subjectId } },
        // openapi-fetch passes FormData straight through to fetch (letting the
        // browser set the multipart boundary) — the generated type expects a
        // `{ file: string }` JSON body since openapi-typescript renders
        // `format: binary` as `string`, so this cast is the documented workaround.
        body: formData as unknown as { file: string },
      });
      if (error) {
        // A 402 means the plan's per-subject document cap is hit — capture it (status
        // lives on the response, not the body) so the UI can show an upgrade prompt
        // instead of a toast. Any other status toasts a friendly message (415/413/
        // generic) — the 402 path stays inline per FRONTEND.md §3.3, so it's the one
        // case that must NOT also fire a toast here.
        const limit = parsePlanLimitError(response.status, error);
        setLimitError(limit);
        const message = friendlyUploadError(response.status);
        if (!limit) toast.error(t("SubjectDetail.uploadErrorTitle"), message);
        throw new Error(message);
      }
      return data;
    },
    onMutate: () => setLimitError(null),
    onSuccess: (data) => {
      if (fileInputRef.current) fileInputRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "documents"] });
      toast.success(
        t("SubjectDetail.uploadSuccessTitle"),
        t("SubjectDetail.uploadSuccessBody", { filename: data.filename }),
      );
    },
    onError: () => {
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
  });

  const deleteDocument = useMutation({
    mutationFn: async (documentId: string) => {
      const { error, response } = await api.DELETE("/subjects/{subject_id}/documents/{document_id}", {
        params: { path: { subject_id: subjectId, document_id: documentId } },
      });
      // 204 No Content on success — openapi-fetch leaves `data` undefined for that,
      // so `error` (not `data`) is what actually signals failure here.
      if (error) throw new Error(friendlyDeleteError(response.status));
    },
    onSuccess: (_data, documentId) => {
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "documents"] });
      const filename = documentsQuery.data?.find((doc) => doc.id === documentId)?.filename;
      toast.success(t("SubjectDetail.deleteSuccessTitle"), filename);
    },
    onError: (error: Error) => {
      toast.error(t("SubjectDetail.deleteErrorTitle"), error.message);
    },
  });

  const backLink = (
    <Link
      href="/subjects"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      {t("Nav.subjects")}
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

  return (
    <div>
      {backLink}

      <div className="mb-8 flex flex-wrap items-center justify-between gap-2">
        <h1 className="min-w-0 text-2xl font-semibold break-words">
          {subjectQuery.isLoading ? t("Common.loading") : subjectQuery.data?.name}
        </h1>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link href={`/subjects/${subjectId}/progress`}>{t("SubjectDetail.progressLink")}</Link>
            }
          />
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link href={`/subjects/${subjectId}/flashcards`}>
                {t("SubjectDetail.flashcardsLink")}
              </Link>
            }
          />
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link href={`/subjects/${subjectId}/quizzes`}>{t("SubjectDetail.quizzesLink")}</Link>
            }
          />
          <Button
            nativeButton={false}
            render={<Link href={`/subjects/${subjectId}/ask`}>{t("SubjectDetail.askLink")}</Link>}
          />
        </div>
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>{t("SubjectDetail.uploadTitle")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
            disabled={uploadDocument.isPending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadDocument.mutate(file);
            }}
          />
          {uploadDocument.isPending && (
            <p className="mt-2 text-sm text-muted-foreground">{t("SubjectDetail.uploading")}</p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">{t("SubjectDetail.processingHint")}</p>
          {limitError && <UpgradePrompt message={limitError.detail} />}
        </CardContent>
      </Card>

      {documentsQuery.isLoading && <p>{t("Common.loading")}</p>}
      {documentsQuery.isError && (
        <p className="text-destructive">{t("SubjectDetail.loadError")}</p>
      )}
      {documentsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">{t("SubjectDetail.empty")}</p>
      )}
      <ul className="flex flex-col gap-2">
        {documentsQuery.data?.map((doc) => (
          <li key={doc.id}>
            <Card>
              <CardContent className="flex flex-col gap-2 py-4">
                <div className="flex items-center justify-between gap-4">
                  <p className="min-w-0 flex-1 truncate font-medium">{doc.filename}</p>
                  <Badge className="shrink-0" variant={documentStatusVariant(doc.status)}>
                    {t(`Progress.status.${doc.status}`)}
                  </Badge>
                  <Button
                    variant="destructive"
                    size="icon-sm"
                    className="shrink-0"
                    aria-label={t("SubjectDetail.deleteAriaLabel", { filename: doc.filename })}
                    disabled={deleteDocument.isPending && deleteDocument.variables === doc.id}
                    onClick={async () => {
                      const ok = await confirm({
                        title: t("SubjectDetail.deleteConfirmTitle", { filename: doc.filename }),
                        description: t("Common.cantUndo"),
                        destructive: true,
                      });
                      if (!ok) return;
                      deleteDocument.mutate(doc.id);
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
                {doc.status === "ready" && doc.summary && (
                  <p className="text-sm text-muted-foreground wrap-break-word">{doc.summary}</p>
                )}
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
