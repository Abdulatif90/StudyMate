/**
 * The content type to upload a file as. Prefers the browser-provided `file.type`, but
 * falls back to a filename-extension lookup when it's empty — some browsers/OSes report
 * an empty type for `.txt`, `.docx`, or `.md`-style files, and the backend rejects an
 * upload whose content type isn't one it can parse (415). Direct-to-R2 uploads sign the
 * presigned PUT with this exact type, so getting it right up front avoids a signature
 * mismatch and a needless 415.
 *
 * Returns `application/octet-stream` when nothing matches — the backend will then return
 * a clear 415 (which the UI surfaces as an unsupported-type message), rather than the
 * upload failing obscurely against R2.
 */
const EXTENSION_CONTENT_TYPES: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  txt: "text/plain",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

export function inferContentType(file: { name: string; type: string }): string {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_CONTENT_TYPES[ext] ?? "application/octet-stream";
}
