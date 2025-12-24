# Repository Guidelines

## Project Structure & Module Organization
- Root: `Makefile`, `.env` (local only), `README.md`.
- Frontend (Next.js + TS): `frontend/` → App Router in `src/app/**`, config in `next.config.ts`, `tailwind.config.mjs`.
- Backend (FastAPI): `server/` → entry `server.py`, routes and utils in `server/app/**`, Python deps in `pyproject.toml` (managed by `uv`).
- Data: ephemeral SQLite (do not commit).

## Build, Test, and Development Commands
- Install deps (frontend + backend): `make sync`
- Run dev (Next.js + backend via concurrently): `make serve` → http://localhost:3000
- Backend only (hot reload): `cd server && uv run server.py`
- Frontend dev only: `cd frontend && npm run dev:next`
- Frontend prod build/start: `cd frontend && npm run build && npm start`
- Lint (frontend): `cd frontend && npm run lint`
- Softnix tool check: `cd server && uv run python test_softnix.py`

## Coding Style & Naming Conventions
- Frontend: TypeScript, 2‑space indent; React components `PascalCase`; files under `src/app/**` follow Next.js app router (`page.tsx`, `layout.tsx`). Use Tailwind utilities; keep UI logic lean and move helpers to `frontend/src/**/utils.ts` when needed.
- Backend: Python 3.11+, PEP8, type hints where practical; modules `snake_case.py`, classes `PascalCase`, functions `snake_case`. Keep FastAPI routers and helpers in `server/app/**`.

## Testing Guidelines
- Backend: ad‑hoc script `server/test_softnix.py` for Softnix API. For new tests, prefer `pytest` with files named `test_*.py`. Target external calls with fakes.
- Frontend: no test runner configured; if adding, prefer `vitest` + `@testing-library/react`. Place tests next to components as `*.test.tsx`.

## Commit & Pull Request Guidelines
- Commits: imperative present (“Add admin routes”), concise subject (<72 chars), details in body when needed. Group logical changes; avoid drive‑by edits.
- PRs: include summary, motivation, and scope; link issues; add screenshots/GIFs for UI changes; note env or migration impacts. Ensure `make sync` and `make serve` succeed locally.

## Security & Configuration Tips
- Secrets: set `OPENAI_API_KEY` via `.env` (untracked) or environment. Never commit secrets.
- CORS/origins: backend enables CORS for local dev—tighten for deployments.
