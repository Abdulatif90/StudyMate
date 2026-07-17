// Pure progress computation for a flashcard review session — no React, no fetching.
// `currentIndex` is 0-based (position in the due-cards list); `totalCards` is the
// session's original due-card count, captured once at session start so it doesn't
// shrink as cards are graded and refetched out of the /due list mid-session.

export interface ReviewProgress {
  current: number; // 1-based position of the card currently shown
  total: number;
  remaining: number; // cards left to grade, including the current one
  isComplete: boolean; // true once every card in the session has been graded
}

export function reviewProgress(totalCards: number, currentIndex: number): ReviewProgress {
  const isComplete = totalCards === 0 || currentIndex >= totalCards;
  return {
    current: isComplete ? totalCards : currentIndex + 1,
    total: totalCards,
    remaining: Math.max(totalCards - currentIndex, 0),
    isComplete,
  };
}
