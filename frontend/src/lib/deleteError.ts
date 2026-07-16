export function friendlyDeleteError(status: number): string {
  if (status === 404) return "This document was already deleted or couldn't be found.";
  return "Couldn't delete this document. Please try again.";
}
