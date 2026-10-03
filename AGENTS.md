# Orion Banking — Base44 dev environment

## Stack
- `OrionBS.1.0.html` — self-contained static demo page (no API calls, no build step). Served on host port 3000.
- `backend/` — FastAPI app (uvicorn, SQLAlchemy 2, Postgres 16, JWT auth). Served on host port 8000 with `--reload`; source is bind-mounted, so backend edits hot-reload without rebuilds.
- The static page and the API are independent: the HTML demo never calls the backend.

## Run
`docker compose -f docker-compose.base44.yml up -d`

## Quirks (fixed during setup)
- `backend/requirements.txt` pinned `psycopg==3.12.0`, which does not exist on PyPI — now pinned to 3.2.13.
- `passlib 1.7.4` crashes with bcrypt ≥ 4.1 (72-byte probe bug) — bcrypt is pinned to 4.0.1.
- Tables are created by `Base.metadata.create_all()` in `backend/app/main.py` at startup; alembic exists but isn't required to boot.

## Verify
- `curl localhost:3000/` serves the demo page.
- `curl localhost:8000/health` → `{"status":"ok"...}`.
- Register/login flow: `POST /auth/register`, `POST /auth/login`, then `GET /accounts/me` with the bearer token. API docs at `http://localhost:8000/docs`.
- Backend tests: `docker compose -f docker-compose.base44.yml exec api sh -c 'pip install -q pytest httpx && pytest'` (tests expect a live DB).
