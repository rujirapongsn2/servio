# Repository Guidelines

## Project Structure & Module Organization
- Root: `docker-compose.yml`, `services.sh`, `start.sh` (compatibility wrapper), `.env` (local only), `README.md`.
- Frontend (Next.js + TS): `frontend/` → App Router in `src/app/**`, config in `next.config.ts`, `tailwind.config.mjs`, `Dockerfile` for containerization.
- Backend (FastAPI): `server/` → entry `server.py`, routes and utils in `server/app/**`, Python deps in `pyproject.toml` (managed by `uv`), `Dockerfile` for containerization.
- Database: PostgreSQL 15 running in Docker container, data persisted in `postgres_data` volume.
- Nginx: Reverse proxy in Docker for routing and SSL termination.

## Build, Test, and Development Commands

### Docker Management (Primary Method)
- **Start all services**: `./services.sh start`
- **Start one service with dependencies**: `./services.sh start frontend` or `./services.sh start backend`
  - Frontend: https://localhost
  - Backend API: https://localhost/api
  - WebSocket: wss://localhost/ws
  - Admin: https://localhost/admin
- **Stop services**: `./services.sh stop` or `./services.sh stop frontend`
- **Restart** (after .env changes): `./services.sh restart` or `./services.sh restart backend`
- **Rebuild** (after code changes):
  - Backend code: `./services.sh rebuild backend`
  - Frontend code: `./services.sh rebuild frontend`
  - Both: `./services.sh rebuild`
- **Update from GitHub and deploy**: `./services.sh update`
- **View logs**: `./services.sh logs` or `./services.sh logs backend`
- **Check status**: `./services.sh status`

### Local Development (Without Docker - Legacy)
- Backend only: `cd server && uv run server.py`
- Frontend only: `cd frontend && npm run dev:next`
- Lint (frontend): `cd frontend && npm run lint`
- Softnix tool check: `cd server && uv run python test_softnix.py`

## Docker Services Architecture
- **nginx**: Reverse proxy (ports 80→8080, 443→8443), routes to frontend/backend
- **postgres**: PostgreSQL 15 database with persistent volume
- **backend**: FastAPI server (Python 3.11) running on port 8000 inside container
- **frontend**: Next.js application (Node 20) running on port 3000 inside container

### Rebuild Requirements
**Must rebuild:**
- Modified Python code in `server/`
- Modified React/Next.js code in `frontend/src/`
- Changed dependencies (`package.json`, `pyproject.toml`)
- Modified Dockerfile

**Only restart needed:**
- Changed `.env` file (API keys, environment variables)
- Modified `nginx/nginx.conf`

## Coding Style & Naming Conventions
- Frontend: TypeScript, 2‑space indent; React components `PascalCase`; files under `src/app/**` follow Next.js app router (`page.tsx`, `layout.tsx`). Use Tailwind utilities; keep UI logic lean and move helpers to `frontend/src/**/utils.ts` when needed.
- Backend: Python 3.11+, PEP8, type hints where practical; modules `snake_case.py`, classes `PascalCase`, functions `snake_case`. Keep FastAPI routers and helpers in `server/app/**`.

## Testing Guidelines
- Backend: ad‑hoc script `server/test_softnix.py` for Softnix API. For new tests, prefer `pytest` with files named `test_*.py`. Target external calls with fakes.
- Frontend: no test runner configured; if adding, prefer `vitest` + `@testing-library/react`. Place tests next to components as `*.test.tsx`.

## Commit & Pull Request Guidelines
- Commits: imperative present ("Add admin routes"), concise subject (<72 chars), details in body when needed. Group logical changes; avoid drive‑by edits.
- PRs: include summary, motivation, and scope; link issues; add screenshots/GIFs for UI changes; note env or migration impacts. Ensure Docker services build and start successfully (`./services.sh rebuild`, then `./services.sh status`) before submitting.

## Security & Configuration Tips
- **Secrets**: Set API keys in `.env` file at project root (untracked). Required: `OPENAI_API_KEY`. Optional: `SOFTNIX_API_KEY`, `GEMINI_API_KEY`. Never commit secrets.
- **Database**: Connection string auto-configured via docker-compose: `postgresql://postgres:postgres@postgres:5432/voice_agents`
- **SSL Certificates**: Auto-generated self-signed certs in `nginx/certs/` for local HTTPS development
- **CORS/origins**: Configure via `ALLOWED_ORIGINS` in `.env`. Backend enables CORS for local dev—tighten for production deployments.
- **Container Security**: All containers run as non-root users with security hardening (no-new-privileges, cap_drop: ALL, read-only filesystems where applicable)
