"use client";

import { useAuth } from "@clerk/nextjs";
import type { Middleware } from "openapi-fetch";
import { useEffect, useRef } from "react";
import { apiClient } from "./client";

/**
 * The typed API client, with every request carrying the caller's Clerk session
 * token as `Authorization: Bearer <token>` — this is what lets FastAPI's
 * `get_current_user_id` dependency verify the request on the backend.
 *
 * Registers the auth middleware once per mount (not on every render, which would
 * stack duplicate middlewares) but always reads the *current* `getToken` via a ref,
 * so a token refresh or session change is picked up without re-registering.
 */
export function useApiClient() {
  const { getToken } = useAuth();
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  useEffect(() => {
    const authMiddleware: Middleware = {
      async onRequest({ request }) {
        const token = await getTokenRef.current();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
        return request;
      },
    };
    apiClient.use(authMiddleware);
    return () => {
      apiClient.eject(authMiddleware);
    };
  }, []);

  return apiClient;
}
