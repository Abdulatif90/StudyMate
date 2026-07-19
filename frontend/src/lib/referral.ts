/**
 * Referral link helpers — the pure logic behind capturing a `?ref=CODE` param and
 * building a share URL. Kept here (not inline in a component) so it's unit-testable.
 *
 * Codes are the backend's 8-char RFC 4648 base32 (A–Z, 2–7); see
 * `backend/app/modules/referral/service.py`. We validate that shape before persisting a
 * captured value so a hand-edited/garbage `?ref=` never gets stored or POSTed — the
 * backend still authoritatively rejects unknown codes (404), this is just an early guard.
 */

const CODE_PATTERN = /^[A-Z2-7]{8}$/;

/** localStorage key holding a pending referral code captured before sign-in completes. */
export const PENDING_REFERRAL_KEY = "studymate.pendingReferral";

/**
 * Read and validate a referral `code` from a URL query string (e.g.
 * `window.location.search`). Case-insensitive; returns the normalized (uppercase) code,
 * or `null` when there's no `ref` param or it isn't a well-formed code.
 */
export function parseRefParam(search: string): string | null {
  const raw = new URLSearchParams(search).get("ref");
  if (raw === null) return null;
  const normalized = raw.trim().toUpperCase();
  return CODE_PATTERN.test(normalized) ? normalized : null;
}

/**
 * Build the shareable sign-up URL for a referral code:
 * `${origin}/sign-up?ref=CODE`. `origin` is expected to have no trailing slash
 * (`window.location.origin` never does).
 */
export function buildReferralShareUrl(origin: string, code: string): string {
  return `${origin}/sign-up?ref=${encodeURIComponent(code)}`;
}
