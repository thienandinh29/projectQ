# MAP — where things are

Keep this file current when adding top-level folders or important modules.
Planned entries are marked _(planned)_ until they exist.

## Repository paths

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Rules and working agreement for Claude, one-owner v2 project (auto-loaded; imports `MAP.md` and `SPEC.md`) |
| `SPEC.md` | What NodeTrail must do: features, behaviors, non-goals |
| `docs/v2/plan-to-tet-2027.md` | **Current plan with status per week** (where the project is) |
| `docs/v2/decision-log.md` | Owner's weekly decision log, in their own words |
| `docs/v2/plan-m0-m1.md` | v2 plan: M0 source catalogue (built), M1 Deep Research on the catalogue, later milestones |
| `docs/archive/contest-2026/` | Contest history: `TEAM.md` (lanes, API contract tables, timeline), `PLAN.md`, `team/`, run sheets and reviews, pitch and mock-demo plan. Code comments that cite `TEAM.md` refer to this copy |
| `specs/` | GitHub Spec Kit: one folder per feature (spec, plan, tasks); `engine/`, `next-item/`, `retrieval/`, `library/`, `remediation/`, `model-test/`, `guardrails/` (P1; includes the labelling protocol), `contracts/review.md` (open contract decisions), `contracts/mocks/` (generated mock JSON for P5, `tests/engine/mocks.py`) |
| `.specify/` | Spec Kit project memory: `memory/constitution.md`; templates planned |
| `docker/` | `LOCAL.md` runbook (one-command start, tests, TEI indexing), `TEI.md` |
| `context/product-brief.vi.md` | Original product brief (Vietnamese) |
| `context/` | Reference material: research, textbook notes, algorithm papers |
| `outputs/` | Generated deliverables, not source code |
| `.claude/settings.json` | Pre-approved commands for Claude Code |
| `.claude/skills/verify/` | `/verify` — run all lint, type checks, tests |
| `.env.example` | Every env var the project uses (copy to `.env`) |
| `docker-compose.yml` | The whole stack in one command: db, migrate, api, worker, sandbox, runner, web; TEI as an opt-in profile (`specs/one-command-start/`) |
| `apps/api/Dockerfile`, `apps/web/Dockerfile` | Images for the API/worker/migrations and the web app |
| `scripts/stack-smoke.sh` | End-to-end checks of a running stack (also the CI `stack` job) |
| `.github/workflows/ci.yml` | CI: ruff, mypy, pytest against a pgvector service, evaluation gates, sandbox escape tests, grader self-test, the full stack |
| `evals/` | Evaluation gates and their committed baselines (`app/evalkit/gates.py`); placement accuracy is the first |
| `runner/` | Code sandbox service: sandbox image and harness, one locked-down container per run, `POST /run`, escape tests (`specs/code-sandbox/`) |
| `apps/api/` | FastAPI backend (uv, Python 3.12): `app/main.py` app factory + `/health` |
| `apps/api/app/config.py` | Settings from repo-root `.env` (pydantic-settings) |
| `apps/api/app/migrate.py` | Applies `supabase/migrations/*.sql` once each (`uv run python -m app.migrate`) |
| `apps/api/tests/` | pytest; `conftest.py` makes a throwaway migrated DB per run |
| `apps/api/app/schemas.py` | Contracts (P1): Knowledge Graph + Items YAML models with validators, `Citation`, every API body |
| `apps/api/app/engine/` | Pure, tested decision logic: `bkt.py` (mastery), `srs.py` (FSRS review scheduling); traced wrappers `update_traced`/`review_traced`; `trace.py` (`DecisionTrace`) |
| `apps/api/app/engine/bkt_fit.py` | EM (Baum-Welch) fitting of BKT parameters from answer sequences, held-out scoring (log loss, Brier, AUC), simulation; data needs in `docs/v2/bkt-fit-eval.md` |
| `apps/api/app/engine/graph.py` | `Graph` (prerequisite DAG: topological order, depth, ancestors/descendants) + `root_cause` to the weakest prerequisite, traced |
| `apps/api/app/evalkit/` | Evaluation helpers (P1): exact intervals and kappa (`stats.py`), the labelled-sample format (`labels.py`), guardrail scoring with notes on what the sample cannot show (`guardrail.py`) |
| `apps/api/app/evalkit/model_checks.py` | Offline H8 G1–G4 screening against P1 contracts; mandatory review remains explicit (`specs/model-test/offline-checks.md`) |
| `apps/api/app/evalkit/model_metrics.py` | H8 receipt scoring: verifier catches/false alarms with intervals, p95 latency, task and combined topic cost; missing evidence remains explicit (`specs/model-test/receipts.md`) |
| `specs/model-test/run-procedure.md` | P1's run procedure for the H8 model test: US$2.00 run cap and US$0.50 per-topic cap (proposals), settings, order, evidence to keep, stop rules |
| `apps/api/tests/engine/test_learning_flow.py` | JSON-replayed placement/remediation/mastery/review flow; optional P3 real grader on an integration checkout; no live DB/worker claim |
| `apps/api/app/engine/path.py` | The next step when nothing just went wrong (`next_step`: resume, overdue review, continue, learn, confirm, done) with a target difficulty; traced |
| `apps/api/app/engine/remediation.py` | Remediation rules after a wrong answer (`remediate`: weakest prerequisite, repeated misconception, practise again) and `resume`; traced |
| `apps/api/app/engine/placement.py` | Graph-walk placement: `next_question`, `gap`, `seed_mastery`; stateless, traced; `verify` re-check on by default |
| `apps/api/app/graders/` | Deterministic grading: MCQ (`mcq.py`), code compared outside the sandbox (`code.py`), runner client, grader self-test |
| `apps/api/app/services/code_practice.py`, `apps/api/app/api/code.py` | Code practice routes `/code/exercise`, `/code/attempts` (mounted when `RUNNER_URL` is set) |
| `apps/api/app/tutor/` | P4 three-level Socratic hints with independent verification and safe release |
| `apps/api/app/research/` | Deep Research agent, allowlisted search/readers, library acquisition and pipeline |
| `apps/api/app/curriculum/` | Course specs (modalities and figure kinds per objective, rubrics, code tests), figures as structured data, ground truth computed from figures (`facts.py`); spec in `specs/curriculum-modalities/` |
| `apps/api/app/sources/` | v2 structured sources: licence from metadata (`licence.py`), OpenStax collection/CNXML parsers (`openstax.py`), catalogue fetch CLI (`fetch.py`); spec in `specs/source-catalog/` |
| `apps/api/app/uploads/` | PDF/DOCX/link readers and upload metadata validation |
| `apps/api/app/content/` | P4 schemas, generation, P3 gateway adapter, canonical conversions and runtime repositories/ports |
| `apps/api/app/guardrails/` | Blind verification, current-hash release gate, human-label metrics; live model acceptance pending |
| `data/guardrails/` | 50 evaluation questions + 20 hints and human annotation templates; human labels pending |
| `data/eval/` | Labelled retrieval question sets (Vietnamese question → answer passage) + format README; scored by `app/rag/evaluate.py` |
| `data/golden/` | Three agent-reviewed topics, 45 pending MCQs and 15 chunks; model/human approval pending |
| `apps/api/app/jobs/` | Committed Postgres queue, durable progress/trail, configurable P3 pipeline factory and P4 runtime processor |
| `apps/api/app/observability/` | Logging setup; structlog/Langfuse integration planned |
| `apps/api/app/rag/` | `notebook.py` (ipynb → chunks), `store.py` (`build_vector_index` after bulk load), `embed.py` (`TeiEmbedder` sync + async, local bge-m3, `make_embedder`; managed-API fallback planned), `chunker.py` (`ParsedDocument` → size-safe `Chunk`s), `library.py` (index every book folder), `retrieve.py` (`Retriever.search` → `Citation`s), `evaluate.py` (retrieval metrics on a labelled question set), `ingest.py` CLI (`--embedder tei|local`, `--build-index`); optional `rerank.py` planned (P1) |
| `data/raw/thinkpython/` | Downloaded Think Python 3e notebooks + `SOURCE_SHA` (git-ignored; re-download to rebuild) |
| `apps/api/app/llm/` | LLM gateway (DeepSeek generation, Gemini verification; legacy Vertex AI, Bedrock and OpenRouter adapters), `routing.yaml`, smoke CLI and setup README |
| `data/courses/` | Example course specs: Python basics, IELTS Academic Writing, introductory statistics |
| `data/sources/` | Open-education allowlist, library manifests and acquisition/index reports; `catalog.yaml` + `catalog-report.json` for v2 structured sources |
| `data/kg/` _(planned)_ | Knowledge Graph YAML fixtures |
| `data/items/` _(planned)_ | MCQ item fixtures with misconception tags |
| `apps/web/` | Next.js web app: topic input, research trail, map, learning, tutor (some steps still use sample data) |
| `apps/web/messages/` | i18n strings (`vi` default, `en`) |
| `supabase/migrations/` | Database schema (Postgres + pgvector); `0001_init.sql` = schema v1, `0002` = chunk provenance (chapter, section, kind, url), `0003` = `halfvec(1024)`, `url` → `source_uri`, HNSW dropped (rebuilt after load), `0004` = `decision_traces` (the "Vì sao?" audit trail) |

| `apps/api/app/research/pipeline.py` | P3 topic orchestration; optional async Retriever with explicit indexed subject, citation identity checks and original reading order; validates P1 KnowledgeGraph before publication |

| `apps/api/app/research/smoke.py` | Explicit live canonical graph/items and blind verification route smoke; preflight reads a small public book chapter without model calls |
| `specs/p3-integration/p3-follow-up.md` | P3 follow-up, validated checks, live blockers and P2/P4 integration instructions |

| `specs/p3-integration/h7-results.md` | Current P3 H7 results after main/P4 integration; audited clean library, mandatory worker retrieval, canonical schemas, model configuration, live prerequisites |
| `data/sources/p3-python-library-audit.json`, `data/sources/p3-h7-readiness.json` | Reproducible local export audit and honest environment/model-call readiness receipts |

| `data/sources/p3-python-query-label-audit.json` | Confirms all 10 P1 query label snippets in the intended book sections, with exact page URLs; no ranked retrieval or held-out tuning |
