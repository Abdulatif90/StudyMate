export function friendlyUploadError(status: number): string {
  if (status === 415) return "That file type isn't supported. Upload a PDF, DOCX, or TXT file.";
  if (status === 413) return "That file is too large — the limit is 20 MB.";
  if (status === 409) return "The upload didn't complete. Please try again.";
  // status 0 is the direct-to-R2 PUT failing (network/CORS) — see uploadDocument.ts.
  if (status === 0) return "Couldn't reach file storage. Check your connection and try again.";
  return "Couldn't upload the file. Please try again.";
}
