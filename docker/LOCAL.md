# Running NodeTrail locally

One command starts everything: database, migrations, API, worker, code sandbox runner and web app
(`docker-compose.yml`, spec in `specs/one-command-start/`). You need Docker (Linux containers) and Git.
Commands run from the repository root and work in bash and PowerShell.

## Start

1. Create `.env` once, by hand: copy `.env.example` to `.env`. Set two values to long random strings
   (any 20+ characters; they never leave your machine):
   - `API_KEY`: shared by the web app and the API.
   - `RUNNER_TOKEN`: shared by the API and the code runner.

   Model keys are optional. Without them the app runs, but generating a new topic fails with a named
   reason. To generate content, add the DeepSeek and Gemini keys and set `WORKER_ARGS=--pipeline`.
2. Start:

   ```bash
   docker compose up -d --build --wait
   ```

3. Open <http://localhost:3000> (web) and <http://localhost:8000/docs> (API; send `x-api-key`).
4. Check it end to end (bash; in PowerShell use Git Bash or WSL):

   ```bash
   API_KEY=<your API_KEY> scripts/stack-smoke.sh
   ```

   It checks API health and the database, key enforcement, the web page, the web-to-API proxy, a code
   exercise graded in the sandbox (right, wrong, infinite loop), and the worker finishing a queued job.

| Service | What it does | Reachable at |
|---|---|---|
| `db` | Postgres 16 + pgvector | `localhost:54322` (tests use it too) |
| `migrate` | Applies `supabase/migrations` once each, then exits | — |
| `api` | FastAPI (`app.main:create_content_app`) | `localhost:8000` |
| `worker` | Claims topic jobs from the Postgres queue | — |
| `sandbox` | Builds the sandbox image for code runs, then exits | — |
| `runner` | Runs learner code, one locked-down container per run, via the Docker socket | compose network only |
| `web` | Next.js app in API mode, calls the API through its server-side proxy | `localhost:3000` |
| `tei` | bge-m3 embeddings; opt-in profile `tei` | `localhost:8080` |

Everything binds to localhost only. The API refuses to start without `API_KEY`, and the runner refuses
to listen beyond localhost without `RUNNER_TOKEN`.

## Stop, logs, reset

```bash
docker compose logs -f api worker
```

```bash
docker compose down
```

`down` keeps the database volume. **Destructive reset** (deletes local data):
`docker compose down --volumes`.

## Tests

The API tests need only the database:

```bash
docker compose up -d --wait db
```

```bash
cd apps/api && uv sync --locked && uv run pytest -q
```

Each run creates and drops its own `nodetrail_test_*` database. The `/verify` skill runs every check.

## Indexing the library with TEI (on your machine)

The embedding model is about 2.3 GB, so it is opt-in. It runs on CPU (8 GB memory limit); see
`docker/TEI.md`.

```bash
docker compose --profile tei up -d --wait tei
```

Fetch the catalogue books and index them into the running database (from `apps/api`, with `uv`):

```bash
uv run python -m app.sources.fetch ../../data/sources/catalog.yaml --out ../../data/library --report ../../data/sources/catalog-report.json
```

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:54322/nodetrail uv run python -m app.rag.library ../../data/library --embedder tei --tei-url http://localhost:8080 --build-index
```

In PowerShell, set `$env:DATABASE_URL = '...'` first instead of the `VAR=value` prefix. Record the time,
the chunk count and peak memory in the decision log.

## Troubleshooting

- **A port is taken** (3000, 8000, 54322): find what holds it and stop that, or change the left-hand
  port in `docker-compose.yml`.
- **`api` keeps restarting:** `docker compose logs api`; usually `API_KEY` is missing from `.env`.
- **A container named `nodetrail-db` already exists** from an older checkout: stop it
  (`docker stop nodetrail-db`) and remove it (`docker rm nodetrail-db`). Its data volume is kept.
- **Code answers return 503:** the runner is down or `RUNNER_TOKEN` differs; `docker compose logs runner`.
