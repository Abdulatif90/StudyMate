import type { components } from "@/lib/api/schema";

type FlashcardProgress = components["schemas"]["FlashcardProgress"];

// The backend already partitions `total` into new/learning/mature with no overlap
// (see progress/service.py's _flashcard_progress) — this only turns that object into
// display rows (label, count, percent-of-total, and which semantic token/status word
// to pair the segment with). It never recomputes or re-buckets a single card; doing
// that client-side would risk silently disagreeing with the backend, the actual
// source of truth for which bucket a card is in.
export interface MasteryRow {
  key: "new" | "learning" | "mature";
  count: number;
  percent: number; // 0-100, rounded; rows sum to ~100 (rounding may drift by ±1-2)
}

const ROW_KEYS: readonly MasteryRow["key"][] = ["new", "learning", "mature"];

export function masteryRows(flashcards: FlashcardProgress): MasteryRow[] {
  const total = flashcards.total;
  return ROW_KEYS.map((key) => {
    const count = flashcards[key];
    const percent = total > 0 ? Math.round((count / total) * 100) : 0;
    return { key, count, percent };
  });
}

// A single headline number for "how much of this deck is well-learned" — 0 for an
// empty deck (no cards yet), not NaN/Infinity.
export function percentMature(flashcards: FlashcardProgress): number {
  if (flashcards.total === 0) return 0;
  return Math.round((flashcards.mature / flashcards.total) * 100);
}
