export function friendlyUploadError(status: number): string {
  if (status === 415) return "That file type isn't supported. Upload a PDF, DOCX, or TXT file.";
  if (status === 413) return "That file is too large — the limit is 20 MB.";
  return "Couldn't upload the file. Please try again.";
}
