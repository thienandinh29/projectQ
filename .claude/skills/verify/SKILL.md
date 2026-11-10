---
name: verify
description: Run all lint, type checks and tests for NodeTrail (API and web) and report results. Use before saying any task is done.
---

Run every check that exists; skip a part only if its folder does not exist yet, and say you skipped it.

1. API (`apps/api`), from that folder:
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run mypy .`
   - `uv run pytest -q`
2. Web (`apps/web`), from that folder:
   - `pnpm lint`
   - `pnpm typecheck`
   - `pnpm test`
3. Report a table: check | pass/fail | key output. Paste the real error output for failures.
   Never claim "done" if anything failed; propose a fix and ask before applying large changes.
