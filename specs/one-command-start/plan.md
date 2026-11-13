# Plan: one-command start

- **API image** (`apps/api/Dockerfile`, context = repository root): Python 3.12 slim, dependencies from `uv.lock`
  (no dev tools), non-root user. The repository layout is kept under `/srv` so paths derived from the source tree
  (migrations, `data/`) resolve as in a checkout. The same image runs the API, the worker and the migration job.
  uv is installed from PyPI, so the build needs no other registry.
- **Web image** (`apps/web/Dockerfile`): pnpm install from the lockfile, `next build`, production dependencies only,
  non-root. Server-side settings (`NODETRAIL_*`) are runtime environment, not baked in.
- **Compose** (`docker-compose.yml`): `migrate` runs to completion before `api` and `worker`; `sandbox` builds the
  sandbox image and exits before `runner`; `web` waits for a healthy `api`. Shared API settings in one anchor;
  `environment` overrides `.env` for addresses inside the network. `API_KEY` and `RUNNER_TOKEN` are not required by
  interpolation (that would break `docker compose up db`), so the services enforce them.
- **Runner:** `bind_problem(host, token)` refuses a non-loopback bind without a token (unit-tested).
- **Checks:** `scripts/stack-smoke.sh` (bash, curl, python3) and a `stack` CI job that builds, starts, checks and
  tears down.
- **Docs:** `docker/LOCAL.md` rewritten as the runbook, including the owner's TEI indexing step.
