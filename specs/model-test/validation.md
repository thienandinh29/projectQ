# P1 evaluation and learner-flow validation — 2026-11-07

Reviewed patch: offline G1–G4 screening, G5–G7 receipt scoring, duplicate item-ID
validation, deterministic default FSRS scheduling and learner-flow replay.

| Check | Result |
|---|---|
| API Ruff lint | Pass |
| API format check | Pass, 63 files |
| API mypy | Pass, 63 source files |
| Full P1 API pytest with Postgres/pgvector | 1,021 passed, 1 skipped, 1 warning |
| Engine/evaluation on isolated ptest 9887d32 + patch | 847 passed |
| Staged whitespace check | Pass |

The skip is the P3-grader variant of the flow test because P3 is absent from the
P1 branch. That variant passed on the isolated ptest checkout. The warning is an
existing Starlette/httpx deprecation. The integration subset excludes DB trace
storage; the complete P1 suite above includes DB-backed tests.

Full tests used a dedicated temporary pgvector/pg16 database, with test-only
`TEST_DATABASE_ADMIN_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
Tests create and remove their own migrated databases. No application config,
credentials, shared database or deployment configuration was changed. This
successful run supersedes earlier results blocked by unavailable Postgres.

Regression coverage includes exact/over-cap monetary values, extra/missing
verifier labels, duplicate item IDs and deterministic scheduling without mutation.
Flow coverage composes placement -> wrong diagnostic -> prerequisite remediation
-> resumed learning -> mastery -> overdue review, with JSON state/trace replay.

This is not live H7 acceptance: real gateway/search calls, full HTTP/database
adapter transactions, worker wiring, TEI latency, retrieval recall and browser
acceptance remain cross-lane work. The noisy-placement 90% target remains unmet.
