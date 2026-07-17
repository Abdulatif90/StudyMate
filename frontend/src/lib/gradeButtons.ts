// Maps a small set of labeled review buttons to SM-2's 0-5 quality scale (the backend's
// app.modules.flashcards.sm2 module) — pins the exact integers sent to
// POST /flashcards/{id}/review so a UI change can't accidentally send a float, a string,
// or an out-of-range value (the backend would 422, but this is the single place that
// contract is defined on the frontend).
//
// Deliberately NOT all six raw SM-2 grades — Anki-style four buttons instead, since
// dumping "grade yourself 0-5" on a learner is exactly the fragmented-input UX SM-2
// implementations avoid. `PASSING_GRADE` mirrors the backend's sm2.PASSING_GRADE (3):
// grades below it are a lapse (resets the schedule), at/above it are a pass (advances
// it) — "Again" is the only lapse button here; Hard/Good/Easy all pass, just with
// different resulting intervals.
export const PASSING_GRADE = 3;

export interface GradeButton {
  label: string;
  grade: number;
}

export const GRADE_BUTTONS: readonly GradeButton[] = [
  { label: "Again", grade: 1 },
  { label: "Hard", grade: 3 },
  { label: "Good", grade: 4 },
  { label: "Easy", grade: 5 },
];

export function isLapseGrade(grade: number): boolean {
  return grade < PASSING_GRADE;
}
