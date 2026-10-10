# AGENTS.md — running Orion Banking in Base44

FastAPI + Jinja2 monolith; the backend serves both the JSON API (`/api/*`) and the
HTML UI (`/*`). All application code lives in `backend/`.

## Run it

```bash
docker compose -f docker-compose.base44.yml up -d --build   # host :3000 → web :8000
docker compose -f docker-compose.base44.yml logs -f web
```

* Dev stack, not the repo's own `backend/docker-compose.yml` (that one only runs Postgres).
* The app runs **from the bind-mounted source** (`./backend:/app/backend`) with
  `uvicorn --reload`, so code edits apply without a rebuild.
* Dependencies are installed into the image built from `Dockerfile.base44`
  (manifest only, no source copy). **Rebuild after `backend/requirements.txt` changes.**
* Health endpoint: `GET /health` (used by the compose healthcheck).
* `SECRET_KEY` comes from the platform-managed `/run/base44/app.env`; the local
  Postgres credentials are inline in the compose file.

## Database and migrations

* Postgres 16 runs as the `db` service; the schema is applied by the one-shot
  `migrate` service (`alembic upgrade head`), and `web` waits for it to complete.
* **The alembic chain only works on Postgres.** Do not "fix" it for SQLite:
  `20241004_overhaul` uses `op.alter_column(..., nullable=False)`, which SQLite
  cannot execute (`near "ALTER": syntax error`), and several migrations rely on
  native enum types. This is pre-existing; the app's own SQLite dev path never
  runs migrations — the lifespan calls `Base.metadata.create_all()` instead.
* Keep migrations dialect-portable when editing them:
  * no SQLite-only functions in raw SQL (`randomblob()`, `hex()`); generate
    values in Python instead,
  * cast string literals to a Postgres enum (`::enum_name`) when backfilling an
    enum column,
  * enum types are created implicitly by `op.create_table()` — an extra explicit
    `sa.Enum(...).create(bind)` raises `type "..." already exists` on Postgres.
* Fresh `docker compose up` on an empty volume applies all 8 revisions cleanly.

## Tests

```bash
docker compose -f docker-compose.base44.yml exec -T web sh -c 'cd /app/backend && python -m pytest tests/ -q'
```

* 179 tests, ~3.5 minutes. They build their own schema with `create_all()` on a
  file-backed SQLite DB (`backend/test_orion.db`), so **passing tests do not prove
  the migrations work** — verify migrations separately.
* CI (`.github/workflows/ci.yml`) runs the same suite on SQLite.

## Verifying the app by hand

```bash
curl -s localhost:3000/health
# register → login → deposit → analytics
curl -s -X POST localhost:3000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"full_name":"QA","email":"qa@example.com","pin":"284917"}'
curl -s -X POST localhost:3000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"qa@example.com","pin":"284917"}'
curl -s -X POST localhost:3000/api/transactions/deposit -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/json' -d '{"amount":500}'
curl -s "localhost:3000/api/analytics/summary?days=90" -H "Authorization: Bearer <token>"
```

The UI pages are server-rendered and call the API with a bearer token from
`localStorage`. `GET /analytics` returns 401 without a token, which is expected.

## Gotchas

* `ENV=dev` starts the APScheduler job that runs due scheduled transfers every
  60s — it needs `SessionLocal` imported in `app/main.py`.
* `backend/scripts/seed.py` populates demo data (`python scripts/seed.py` from
  `backend/`); it respects an already-set `DATABASE_URL`, so inside the container
  it seeds the Postgres service.
* The app does not check the `Host` header, and the UI is same-origin on port
  3000, so no host/origin allowlist is needed in the sandbox.
