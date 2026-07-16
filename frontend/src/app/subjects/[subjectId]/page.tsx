"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useApiClient } from "@/lib/api/useApiClient";
import { documentStatusVariant } from "@/lib/documentStatus";
import { documentsRefetchInterval } from "@/lib/documentsPolling";
import { friendlyUploadError } from "@/lib/uploadError";

export default function SubjectDetailPage() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const api = useApiClient();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

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
      if (error) throw new Error(friendlyUploadError(response.status));
      return data;
    },
    onSuccess: () => {
      setUploadError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["subjects", subjectId, "documents"] });
    },
    onError: (error: Error) => {
      setUploadError(error.message);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
  });

  const backLink = (
    <Link
      href="/subjects"
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Subjects
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

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      {backLink}

      <div className="mb-8 flex flex-wrap items-center justify-between gap-2">
        <h1 className="min-w-0 text-2xl font-semibold break-words">
          {subjectQuery.isLoading ? "Loading…" : subjectQuery.data?.name}
        </h1>
        <Button
          className="shrink-0"
          nativeButton={false}
          render={<Link href={`/subjects/${subjectId}/ask`}>Ask</Link>}
        />
      </div>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Upload a document</CardTitle>
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
            <p className="mt-2 text-sm text-muted-foreground">Uploading…</p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Processing (parsing, chunking, embedding) runs in the background — a new
            document shows as “pending” until it’s ready.
          </p>
          {uploadError && <p className="mt-2 text-sm text-destructive">{uploadError}</p>}
        </CardContent>
      </Card>

      {documentsQuery.isLoading && <p>Loading…</p>}
      {documentsQuery.isError && (
        <p className="text-destructive">Couldn&apos;t load documents.</p>
      )}
      {documentsQuery.data?.length === 0 && (
        <p className="text-muted-foreground">No documents yet — upload one above.</p>
      )}
      <ul className="flex flex-col gap-2">
        {documentsQuery.data?.map((doc) => (
          <li key={doc.id}>
            <Card>
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <p className="min-w-0 flex-1 truncate font-medium">{doc.filename}</p>
                <Badge className="shrink-0" variant={documentStatusVariant(doc.status)}>
                  {doc.status}
                </Badge>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
