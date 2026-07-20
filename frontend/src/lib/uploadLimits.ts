/**
 * Client-side copy of the document upload size cap.
 *
 * MUST stay in sync with the backend cap in
 * `backend/app/modules/documents/service.py` → `MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024`.
 * There is no shared source of truth across the Python/TS boundary, so these two are
 * INDEPENDENT — if you change one, change the other. The backend check stays as the real
 * (defense-in-depth) guard; this copy exists so the browser can reject an oversize file
 * BEFORE it wastes a full direct-to-R2 upload only to be rejected with a 413 at confirm.
 */
export const MAX_UPLOAD_MB = 20;
export const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
