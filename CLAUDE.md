@MAP.md
@SPEC.md

# NodeTrail v2 (projectQ)

AI tutor for any subject. The learner states a goal ("Tôi muốn học Python") or uploads a document; NodeTrail
builds a Knowledge Graph from trusted textbooks and runs the loop assess → learn → practice → adjust → review.
Mascot: **Sena** the monkey. Full brief: `context/product-brief.vi.md`.

This repository continues the NodeTrail contest build (team repo `thienandinh29/SenaEmpire36`, frozen after the
2026-11-08 competition) as one owner's project. The contest plan is archived in `docs/archive/contest-2026/`;
read it for history only, its lanes, timeline and freeze rules no longer apply.

## Owner & working agreement
- One owner (student, aspiring ML engineer) working with an AI coding agent.
- **Current goal:** the v2 milestones in `docs/v2/plan-m0-m1.md`: M0 structured source catalogue → M1 Deep Research
  on the catalogue → M2 real learning loop through the UI → M3 measurements → M4 AI teacher (slides, whiteboard)
  driven by the engine. Each milestone must run for real before the next starts; no sample data presented as real.
- **Reply in the owner's language** (Vietnamese in chat is fine); detailed answers with the reasoning behind decisions.
- **Ask before** pushing, adding dependencies, deleting data, or making architectural changes. Commit small, tested
  steps on a feature branch; `main` changes through pull requests with green CI. Never force push.
- **Run tests/lint before saying anything is done** (`/verify`). Report failures honestly with output.
- Spec Kit before code for new routes, contract fields or modules: `specs/<feature>/` with spec, plan, tasks
  (one page each). Bug fixes and small changes inside an existing spec are exempt.

## Language rules
- All code, identifiers, comments, commit messages, and dev docs: **English**.
- Product is for **Vietnamese learners**: all user-facing UI text, Sena's dialogue, tutor responses and sample
  content default to **Vietnamese**. Keep UI strings in i18n files (`vi` default, `en` secondary).
- Handle Vietnamese text correctly: UTF-8 everywhere, NFC normalization, diacritic-aware search/tokenization.

## Core architecture principle
LLM is **not** the decision maker. It sits inside a harness:
- **Learning Engine** decides what to learn next: Bayesian Knowledge Tracing, rule engine (graph-walk placement,
  root-cause remediation), FSRS. Pure functions, unit-tested, every decision returns a `DecisionTrace`.
- **Graders** score work objectively: answer keys now (MCQ); test cases and rubrics later.
- **LLM + RAG** only explains and generates, always with citations to source chunks. No citation → not a fact.
- **Verification gate:** a model of a different family answers each generated item blind from the cited chunks;
  unverified items are never served. The gate reduces errors, it does not remove them: keep human review and
  measured catch rates on the roadmap.
- Socratic tutor never hands over the final answer. Sena praises only real mastery, never speed or streaks.

## Sources
- Prefer structured sources whose licence and chapter order are machine-readable (`apps/api/app/sources/`,
  `data/sources/catalog.yaml`). The HTML crawler (`apps/api/app/research/`) remains a second route.
- Record the licence of every source; never use NoDerivatives licences; flag NonCommercial ones.

## Stack
- Web: `apps/web` — Next.js App Router, TypeScript strict, Tailwind, React Flow + `dagre`.
- API: `apps/api` — Python 3.12, FastAPI, Pydantic v2, uv. Jobs in a Postgres `topic_jobs` queue with a separate
  worker; never long work inside a request; SSE progress with a heartbeat.
- Data: Postgres + pgvector (`halfvec(1024)`); migrations in `supabase/migrations/`, additive only.
- Embeddings: BAAI/bge-m3 (1024 dims) served by TEI behind `Embedder`. Changing the model requires re-indexing.
- LLM: only through `apps/api/app/llm/gateway.py` with `routing.yaml`; the verifier is always a different model
  family from the generator. Never call an LLM SDK or HTTP API directly from features.

## Code conventions
- Python: full type hints, `ruff` (lint + format), `pytest` and `mypy` clean.
- TypeScript: `strict: true`, no `any`, ESLint + Prettier, Vitest for logic.
- Small modules, pure functions for algorithms (BKT/FSRS/Elo) so they are testable without DB or LLM.
- Secrets only in `.env` (never commit, never read it, never paste in chat). Document every variable in
  `.env.example`.

## Folders
- `context/` — reference material (brief, research). `docs/v2/` — current plan. `docs/archive/` — contest history.
- `outputs/` — generated deliverables (reports, exports, diagrams). Not source code.
