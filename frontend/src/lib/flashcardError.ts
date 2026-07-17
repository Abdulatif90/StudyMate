// Maps the flashcard generate endpoint's real HTTP statuses to friendly messages. These
// codes (422 no material, 502 generation failure) aren't in the generated typed error
// shape — FastAPI doesn't document hand-raised HTTPExceptions — so we read
// response.status directly, same pattern as friendlyQuizError / friendlyUploadError.
export function friendlyFlashcardError(status: number): string {
  if (status === 422) {
    return "This subject has no processed material yet. Upload a document and wait for it to be ready, then try again.";
  }
  if (status === 502) {
    return "Couldn't generate flashcards right now. Please try again.";
  }
  return "Something went wrong generating flashcards. Please try again.";
}
