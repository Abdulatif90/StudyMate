import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** Base URL comes from NEXT_PUBLIC_API_URL (frontend/.env.local) — the FastAPI
 * backend's origin must also be in its CORS_ORIGINS for requests here to succeed. */
export const apiClient = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});
