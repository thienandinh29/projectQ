# Spec: one-command start

Week 2 of `docs/v2/plan-to-tet-2027.md`.

## Problem
Running NodeTrail took several terminals and manual steps (database, migrations, API, worker, runner, web), each
with its own settings. A new machine, a reviewer or a collaborator could not start it reliably.

## Behaviour
1. With a `.env` that sets `API_KEY` and `RUNNER_TOKEN`, `docker compose up -d --build --wait` starts the database,
   applies migrations once, then the API, worker, code runner and web app, and returns when all are healthy.
2. The web app runs in API mode and reaches the API through its server-side proxy; the key never reaches the browser.
3. Services reach each other by service name; values in `.env` written for a host setup (`DATABASE_URL`, `TEI_URL`)
   cannot break this.
4. Nothing listens beyond localhost. The API refuses to start without `API_KEY`; the runner refuses to listen beyond
   loopback without `RUNNER_TOKEN`.
5. No model keys are needed to start. Without them a topic job fails with a named reason; with keys and
   `WORKER_ARGS=--pipeline` the worker generates and verifies content.
6. The embedding server (TEI, about 2.3 GB) is opt-in through a compose profile.
7. `scripts/stack-smoke.sh` checks the running stack end to end; CI runs it on every push.
8. `docker compose up db` alone still works for the test suite.

## Not in scope
Cloud deployment, TLS, image publishing, smaller web image (Next.js standalone output), indexing inside the stack.
