# StudyMate

AI study assistant — upload your study materials and get **cited answers, auto-summaries,
quizzes, and spaced-repetition flashcards**. Multilingual, built for global students.

## Stack
- **Backend:** Python 3.12 · FastAPI · SQLModel · Neon Postgres + pgvector · Clerk (auth) ·
  Inngest (jobs) · Cohere (embeddings) · Claude/Anthropic (generation) · R2 · Polar (billing)
- **Frontend:** Next.js 15 · React 19 · TypeScript · Tailwind + shadcn/ui · TanStack Query · next-intl

## Backend — local dev
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
pytest tests
```
API: http://localhost:8000 · Docs: http://localhost:8000/docs

## Project docs
- `CLAUDE.md` — conventions (read before contributing)
- `docs/plan.md` — architecture & roadmap
- `docs/PROGRESS.md` — current state / next steps
- `docs/DECISIONS.md` — key decisions (ADR)
- `docs/WORKLOG.md` — log of completed work
