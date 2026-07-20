# DEPLOYMENT.md — Vercel deploy runbook (frontend + backend)

Step-by-step runbook for deploying StudyMate to **Vercel** (both the Next.js frontend and
the FastAPI backend). This does not create any accounts or set any real secrets — it is the
config + procedure. For the one-time live/webhook/browser tasks that come *after* a first
deploy (apply the pending Neon migration, register webhooks, add `CLERK_SECRET_KEY`, browser
click-through), follow [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) — this doc cross-refs it
rather than duplicating it.

---

## 0. Is all-Vercel viable? (verified against Vercel's live docs)

**Yes — all-Vercel is viable, including the FastAPI backend.** The three make-or-break
questions were checked against Vercel's current docs (July 2026), not from memory:

| Question | Verified answer | Source |
| --- | --- | --- |
| Python FastAPI (ASGI) on Vercel? | Yes. A FastAPI `app` at a supported entrypoint becomes a single Vercel Function on **Fluid compute** by default. `requirements.txt` at the project root is installed automatically. | [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python) |
| **SSE streaming on the Python runtime?** | **Yes.** Streaming is supported for the Python runtime (GA since Jan 5, 2025). Enable it as the default with env var `VERCEL_FORCE_PYTHON_STREAMING=1`. This is what makes the Ask `/…/ask/stream` SSE endpoint work. | [Python streaming changelog](https://vercel.com/changelog/streaming-is-now-supported-in-vercel-functions-for-the-python-runtime) |
| **Function max duration?** | With Fluid compute (default): **Hobby 300 s** (default & max), **Pro 300 s default / 800 s max**. Without Fluid: Hobby 10 s/60 s, Pro 15 s/300 s. A timeout returns 504 `FUNCTION_INVOCATION_TIMEOUT`. | [Function limits](https://vercel.com/docs/functions/limitations), [Duration config](https://vercel.com/docs/functions/configuring-functions/duration), [Fluid defaults](https://vercel.com/changelog/higher-defaults-and-limits-for-vercel-functions-running-fluid-compute) |
| Inngest ingest job on Vercel? | Yes. Inngest Cloud calls the deployed `/api/inngest` endpoint; the Vercel↔Inngest integration auto-sets the keys and syncs on deploy. Recommended `maxDuration` 300 s; Inngest **steps** split the parse→embed→summarize work so no single invocation is long. | [Deploy Inngest to Vercel](https://www.inngest.com/docs/deploy/vercel), [Sync app](https://www.inngest.com/docs/apps/cloud) |

**Fit check for our workloads** (all well within the 300 s Hobby limit):
- Ask SSE stream — a few seconds; streaming works, so tokens flush incrementally.
- Research agent loop — bounded ~5–20 s (`MAX_ITERATIONS = 5`).
- Inngest document processing — split across Inngest steps; each step is its own short
  invocation.

> **Large-file upload — the one Vercel limit we DID hit, now resolved.** Vercel serverless
> functions cap the request body at **~4.5 MB**, so streaming an upload *through* the backend
> function 413'd at the edge for any file between 4.5 MB and the 20 MB app limit (the browser
> saw it as a CORS error — the edge 413 carries no CORS header). Fixed **without leaving
> Vercel**: document upload now uses **presigned direct-to-R2 upload** — the browser `PUT`s the
> file straight to Cloudflare R2 via a short-lived presigned URL (`POST
> /subjects/{id}/documents/presign` → PUT to R2 → `POST /subjects/{id}/documents/{id}/confirm`,
> which HEADs the object to enforce the 20 MB cap and enqueues the same Inngest job). The bytes
> never traverse the function, so the 4.5 MB cap no longer applies and the full 20 MB limit
> works. **This requires a one-time R2 bucket CORS policy** (the browser PUT is cross-origin) —
> see `RELEASE_CHECKLIST.md` **§A2** for the exact policy JSON and the manual dashboard step;
> the fallback in §8 is *not* needed for this.

> **Fallback (documented for honesty, but NOT required):** if streaming or the ingest job
> ever proved unviable on Vercel's Python runtime, the recommended fallback is to keep the
> **frontend on Vercel** and move the **FastAPI backend to a long-running host**
> (Render / Railway / Fly.io) — the app already runs under plain `uvicorn app.main:app`, so
> it deploys there with a one-line start command and no code change; only `NEXT_PUBLIC_API_URL`
> (frontend) and `CORS_ORIGINS` (backend) point at the new backend origin. See §8. **As of
> this verification the fallback is not needed** — Vercel's Python runtime covers both SSE
> streaming and the Inngest ingest job.

---

## 1. Repository layout for two Vercel projects

This is a monorepo. Create **two** Vercel projects, both importing the same Git repo, each
with a different **Root Directory**:

| Vercel project | Root Directory | Framework preset | Notes |
| --- | --- | --- | --- |
| `studymate-web` (frontend) | `frontend` | Next.js (auto-detected) | Zero-config build. |
| `studymate-api` (backend) | `backend` | Other / Python (auto-detected via `vercel.json` + `requirements.txt`) | Becomes one Python Function. |

Deploy from the `main` branch (production) — the repo's own `main ← develop ← feature/*`
flow is unchanged; Vercel builds preview deployments for other branches/PRs automatically.

---

## 2. Backend project (`studymate-api`)

### 2.1 Files already in the repo (no action, just FYI)

- `backend/api/index.py` — the Vercel entrypoint. It only **re-exports** the existing app
  (`from app.main import app`); it does not redefine it, so local `uvicorn app.main:app`
  is untouched.
- `backend/pyproject.toml` → `[tool.vercel] entrypoint = "api.index:app"` — pins that single
  entrypoint (no ambiguity with the auto-detectable `app/main.py`).
- `backend/vercel.json` — sets `functions."api/index.py".maxDuration = 300`.
- `backend/requirements.txt` — installed automatically by Vercel from the project root.

### 2.2 Python version

Vercel's Python runtime is used automatically. Confirm the runtime is **Python 3.12** in the
project's Settings (the repo declares `requires-python = ">=3.12"`). If Vercel's default
differs, pin it per Vercel's Python runtime docs.

### 2.3 Enable streaming (required for the Ask SSE endpoint)

Add env var **`VERCEL_FORCE_PYTHON_STREAMING=1`** to the backend project (Production, and
Preview if you test streaming there). Redeploy for it to take effect.

### 2.4 Environment variables (backend project → Settings → Environment Variables)

Set each of these from `backend/.env.example` (placeholders there; real values here). Scope
to **Production** (and Preview if you run a staging backend). Never paste a secret into the
repo.

| Var | Purpose | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Neon Postgres + pgvector | Use Neon's **pooled** connection string (pgbouncer host, `…-pooler.…`, `sslmode=require`) — serverless functions open many short-lived connections; the pooler prevents exhausting Neon's direct-connection limit. |
| `CLERK_JWKS_URL`, `CLERK_ISSUER` | Clerk JWT verification (JWKS) | Same Clerk app as the frontend. |
| `CLERK_SECRET_KEY` | Assignment roster (Clerk Backend API) | Optional; unset → roster endpoint returns 503, no crash. See `RELEASE_CHECKLIST.md` §C1. |
| `COHERE_API_KEY` | Embeddings | |
| `ANTHROPIC_API_KEY` | Claude generation + OCR vision | |
| `TAVILY_API_KEY` | Research web search | |
| `INNGEST_EVENT_KEY`, `INNGEST_SIGNING_KEY` | Inngest | Auto-set by the Inngest↔Vercel integration (§4). |
| `INNGEST_SERVE_ORIGIN` | Stable Inngest serve URL (optional) | Set to the backend's public origin if using a custom domain (§4). |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Cloudflare R2 file storage | |
| `POLAR_ACCESS_TOKEN`, `POLAR_SERVER`, `POLAR_WEBHOOK_SECRET`, `POLAR_PRODUCT_ID_PRO`, `POLAR_PRODUCT_ID_BUSINESS`, `POLAR_PRODUCT_ID_TEAM` | Billing | For real charges set `POLAR_SERVER=production` + production tokens/products/secret (`RELEASE_CHECKLIST.md` §B2). |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | Telegram bot | `TELEGRAM_WEBHOOK_SECRET` must be set in prod (unset = unverified webhook, dev-only). |
| `SENTRY_DSN` | Backend error monitoring | Optional. |
| `CORS_ORIGINS` | Allowed browser origins | **Set to the real frontend origin(s)** — see §5. |
| `VERCEL_FORCE_PYTHON_STREAMING` | Python SSE streaming | `1` (§2.3). |
| `ENVIRONMENT` | App environment flag | `production`. |

---

## 3. Frontend project (`studymate-web`)

Next.js is native on Vercel — zero build config, no `frontend/vercel.json` needed. Only env
vars matter. Set from `frontend/.env.local.example`:

| Var | Purpose | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk sign-in UI | Same Clerk app as the backend. |
| `CLERK_SECRET_KEY` | Clerk server helpers (frontend) | |
| `NEXT_PUBLIC_API_URL` | Backend base URL | The deployed backend origin, e.g. `https://studymate-api.vercel.app` or `https://api.yourdomain.com`. |
| `NEXT_PUBLIC_SENTRY_DSN` | Frontend Sentry (optional) | A DSN is not a secret. |
| `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST` | Product analytics (optional) | Host must be an API host (`https://us.i.posthog.com`), not a dashboard URL. |

> `NEXT_PUBLIC_*` vars are inlined at **build time** — changing one requires a redeploy.

---

## 4. Inngest Cloud (async document processing)

1. In the Inngest dashboard, use the **Vercel integration** ("Connect Account" → select the
   `studymate-api` project). It auto-sets `INNGEST_EVENT_KEY` / `INNGEST_SIGNING_KEY` and
   syncs the app on each deploy using the deployment URL.
2. The app serves its functions at **`/api/inngest`** (`inngest.fast_api.serve` in
   `app/main.py`) — Inngest Cloud calls that endpoint to run `process-document`.
3. **Deployment Protection caveat:** Vercel enables Deployment Protection on production/preview
   URLs by default, which blocks Inngest from reaching the serve endpoint. Either disable it
   for this project or configure a Protection Bypass. For a stable custom-domain serve URL,
   set `INNGEST_SERVE_ORIGIN` to the backend origin.
4. If not using the integration, manually paste the serve URL
   (`https://<backend-origin>/api/inngest`) in Inngest Cloud → **Sync App**.

---

## 5. CORS / allowed origins (backend change: env only, no code change)

The backend already reads allowed origins from an env var — **no code change is needed.**
`app/core/config.py` exposes `cors_origins` (comma-separated) → `cors_origin_list`, consumed
by `CORSMiddleware` in `app/main.py`. For production:

- Set `CORS_ORIGINS` on the **backend** project to the real frontend origin(s), comma-separated,
  no trailing slash — e.g. `https://studymate.vercel.app,https://app.yourdomain.com`. Include
  both the custom domain and the `*.vercel.app` URL if both are reachable.
- Leaving it unset falls back to `http://localhost:3000` (dev only), which will block the
  production browser — so this must be set.

---

## 6. Database migrations for production (manual / CI step)

Vercel does **not** run Alembic. Migrations are applied out-of-band against the prod Neon URL
— the build has intentionally never auto-run them.

```bash
# from backend/, with DATABASE_URL pointed at the PROD Neon branch (direct, non-pooled URL
# is fine and preferred for DDL):
alembic current        # see where prod is
alembic upgrade head   # apply all pending migrations
alembic current        # confirm == alembic heads
```

Run this **before/with the first deploy**, and again whenever a deploy includes a new
migration. Note: per `RELEASE_CHECKLIST.md` §A, Neon is currently **one migration behind head**
(`c1d2e3f4a5b6`) — apply it. Options: run locally against the prod URL, or add a CI job / a
one-off `vercel` build step; keep it a deliberate, gated action, never automatic on every deploy.

---

## 7. Post-deploy live wiring (see RELEASE_CHECKLIST.md — not duplicated here)

Once both projects are deployed and the domains are known, do the live steps in
[`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md):

- **§A** — apply the pending Neon migration (also §6 above).
- **§B1** — register the **Telegram** webhook to `https://<backend-origin>/telegram/webhook`
  with `secret_token` == `TELEGRAM_WEBHOOK_SECRET`.
- **§B2** — register the **Polar** webhook to `https://<backend-origin>/billing/webhook`
  (production dashboard, `subscription.*` events) and switch `POLAR_SERVER=production`.
- **§C** — add `CLERK_SECRET_KEY` and confirm every per-environment key.
- **§D / §E** — deliberate observability capture + the batched real-browser click-through.

**Custom domains:** add them per project in Vercel → Settings → Domains (e.g.
`app.yourdomain.com` → frontend, `api.yourdomain.com` → backend). After assigning them,
update `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`, the Telegram/Polar webhook URLs, and (optionally)
`INNGEST_SERVE_ORIGIN` to the custom domains, then redeploy.

---

## 8. Fallback: backend on a long-running host (only if ever needed)

Not required (see §0). If a Vercel constraint ever bites (e.g. a workload exceeding the 300 s
Hobby limit, or a need for persistent connections), keep the frontend on Vercel and deploy the
backend to Render / Railway / Fly.io:

- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (the app already runs
  this way — `api/index.py` and `vercel.json` are simply ignored off-Vercel).
- **Build:** `pip install -r requirements.txt` (root `backend/`).
- Set the same env vars from §2.4 in that host's secret store.
- Point `NEXT_PUBLIC_API_URL` (frontend) and `CORS_ORIGINS` (backend) at the new backend
  origin; point the Inngest serve URL, Telegram/Polar webhooks at it too.

No application code changes either way — the entrypoint files are additive and host-agnostic.

---

## Sources (Vercel / Inngest docs consulted)

- FastAPI on Vercel — https://vercel.com/docs/frameworks/backend/fastapi
- Python runtime — https://vercel.com/docs/functions/runtimes/python
- Python streaming (GA) — https://vercel.com/changelog/streaming-is-now-supported-in-vercel-functions-for-the-python-runtime
- Function limits — https://vercel.com/docs/functions/limitations
- Duration configuration — https://vercel.com/docs/functions/configuring-functions/duration
- Fluid compute defaults — https://vercel.com/changelog/higher-defaults-and-limits-for-vercel-functions-running-fluid-compute
- Deploy Inngest to Vercel — https://www.inngest.com/docs/deploy/vercel
- Sync your Inngest app — https://www.inngest.com/docs/apps/cloud
