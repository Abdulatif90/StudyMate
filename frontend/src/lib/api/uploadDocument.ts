import type { Client } from "openapi-fetch";
import type { components, paths } from "./schema";
import { inferContentType } from "@/lib/inferContentType";
import { MAX_UPLOAD_SIZE_BYTES } from "@/lib/uploadLimits";

type DocumentRead = components["schemas"]["DocumentRead"];
type ApiClient = Client<paths>;

/**
 * Where an upload failed, plus the HTTP status when there is one. `kind: "put"` is the
 * direct-to-R2 PUT (a network/CORS failure — most likely the R2 bucket CORS policy not
 * yet allowing PUT from this origin; see docs/RELEASE_CHECKLIST.md), which has no HTTP
 * status from our API, so `status` is 0 there. The page maps `status` to a friendly
 * message and, for the presign step, to the 402 plan-limit upgrade prompt.
 */
export class UploadError extends Error {
  constructor(
    readonly status: number,
    readonly kind: "size" | "presign" | "put" | "confirm",
    /** The parsed error body from our API (used to render the 402 upgrade prompt). */
    readonly body?: unknown,
  ) {
    super(`Upload failed at ${kind} (${status})`);
    this.name = "UploadError";
  }
}

/** PUT the raw file straight to R2 via the presigned URL, reporting upload progress.
 * Uses `XMLHttpRequest` (not `fetch`) because only XHR exposes upload-progress events.
 * The `Content-Type` MUST match the type the presigned URL was signed with, or R2
 * rejects the signature. No `Authorization` header — the signature IS the auth. */
function putFileToR2(
  url: string,
  file: File,
  contentType: string,
  onProgress: (percent: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", contentType);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new UploadError(0, "put"));
    };
    xhr.onerror = () => reject(new UploadError(0, "put"));
    xhr.onabort = () => reject(new UploadError(0, "put"));

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.send(file);
  });
}

/**
 * Upload a document via the presigned direct-to-R2 flow (three steps):
 *   1. `POST .../documents/presign` — validate access/type, get a presigned PUT URL.
 *   2. `PUT` the file straight to R2 (bypasses the backend function's ~4.5 MB body cap,
 *      so files up to the 20 MB limit work), reporting progress.
 *   3. `POST .../documents/{id}/confirm` — the backend HEADs the object, enforces the
 *      20 MB cap, creates the `pending` row, and enqueues processing.
 *
 * Throws `UploadError` (carrying the failing step + HTTP status + parsed body) so the
 * caller can render step-appropriate messages and the 402 plan-limit upgrade prompt.
 */
export async function uploadDocument(
  api: ApiClient,
  params: { subjectId: string; file: File; language: string },
  onProgress: (percent: number) => void,
): Promise<DocumentRead> {
  const contentType = inferContentType(params.file);
  const filename = params.file.name || "untitled";

  // Client-side size guard — reject BEFORE any network call (before presign) so a file
  // over the cap is never PUT to R2 only to be rejected by the backend's confirm-step
  // HEAD check with a 413, wasting the whole upload. Thrown as status 413 so the caller
  // maps it to exactly the same "too large" copy as a server-side 413. The backend check
  // stays as the authoritative guard; this is a UX shortcut. See lib/uploadLimits.ts,
  // which MUST stay in sync with documents/service.MAX_UPLOAD_SIZE_BYTES.
  if (params.file.size > MAX_UPLOAD_SIZE_BYTES) {
    throw new UploadError(413, "size");
  }

  const presign = await api.POST("/subjects/{subject_id}/documents/presign", {
    params: { path: { subject_id: params.subjectId } },
    body: { filename, content_type: contentType },
  });
  if (presign.error || !presign.data) {
    throw new UploadError(presign.response.status, "presign", presign.error);
  }

  await putFileToR2(presign.data.upload_url, params.file, contentType, onProgress);

  const confirm = await api.POST("/subjects/{subject_id}/documents/{document_id}/confirm", {
    params: {
      path: { subject_id: params.subjectId, document_id: presign.data.document_id },
    },
    body: { filename, content_type: contentType, language: params.language },
  });
  if (confirm.error || !confirm.data) {
    throw new UploadError(confirm.response.status, "confirm", confirm.error);
  }
  return confirm.data;
}
