# MAP — where things are

Keep this file current when adding top-level folders or important modules.
Planned entries are marked _(planned)_ until they exist.

## Repository paths

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Rules and working agreement for Claude, one-owner v2 project (auto-loaded; imports `MAP.md` and `SPEC.md`) |
| `SPEC.md` | What NodeTrail must do: features, behaviors, non-goals |
| `docs/v2/plan-english-pack.md` | **Current plan: the English pack in phases, with gates and status** (where the project is) |
| `docs/v2/english-pack-proposal.vi.md` | The owner's proposal for the English pack (Vietnamese): why, components, metrics, risks |
| `docs/v2/plan-to-tet-2027.md` | Superseded weekly plan (weeks 0–2 done); kept for history and the maths outline |
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
| `docker-compose.yml` | The whole stack in one command: db, migrate, api, worker, sandbox, runner, web; TEI, LanguageTool (`writing`) and the scorer (`scoring`) as opt-in profiles (`specs/one-command-start/`) |
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
| `apps/api/app/graders/` | Deterministic grading: MCQ (`mcq.py`), typed answers exact after normalisation (`typed.py`, normaliser extended by the owner), code compared outside the sandbox (`code.py`), runner client, grader self-test |
| `apps/api/app/vocabulary/`, `apps/api/app/services/vocabulary.py`, `apps/api/app/api/vocab.py` | Vocabulary (spec `specs/vocabulary/`): word list models and checks, items built from a word by id (meaning, gap-fill, collocation, word form), FSRS cards per learner and word, routes `/vocab/session`, `/vocab/answers` |
| `apps/api/app/services/code_practice.py`, `apps/api/app/api/code.py` | Code practice routes `/code/exercise`, `/code/attempts` (mounted when `RUNNER_URL` is set) |
| `apps/api/app/tutor/` | P4 three-level Socratic hints with independent verification and safe release |
| `apps/api/app/research/` | Deep Research agent, allowlisted search/readers, library acquisition and pipeline |
| `apps/api/app/curriculum/` | Course specs (modalities and figure kinds per objective, rubrics, code tests, CEFR level per concept, hidden nodes under milestones via `part_of`), figures as structured data, ground truth computed from figures (`facts.py`), course checker CLI (`check.py`); specs in `specs/curriculum-modalities/`, `specs/english-course/` |
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
| `data/courses/` | Course specs: `english-ielts.yaml` (first real course: grammar roadmap of milestones with hidden nodes, A1–C1, starter draft), Python basics, IELTS Academic Writing, introductory statistics |
| `data/sources/` | Open-education allowlist, library manifests and acquisition/index reports; `catalog.yaml` + `catalog-report.json` for v2 structured sources; `english-candidates.yaml` (English sources awaiting licence checks, rules in `app/sources/candidates.py`) |
| `data/vocabulary/` | Word lists: `core-seed.yaml` (30 authored words A2–C1, status draft until the owner reviews it) |
| `data/kg/` _(planned)_ | Knowledge Graph YAML fixtures |
| `data/items/` | Authored grammar items per course: `english-ielts.yaml` (76 draft MCQs, 4 per hidden node, a misconception on every wrong option); `misconceptions.vi.yaml` (each misconception explained in Vietnamese, draft) |
| `apps/api/app/engine/milestones.py` | Milestones and hidden nodes: status, milestone-test outcome (pass, gap, fail), what to learn next, level test on milestones, level estimate; traced (`specs/level-test/`) |
| `apps/api/app/services/grammar.py`, `apps/api/app/api/grammar.py` | Grammar roadmap API: `/level-tests`, `/roadmap`, `/milestones/{slug}/tests`, `/nodes/{slug}/practice`, `/grammar-runs/{id}/answers`; draft items only for `DRAFT_ITEM_LEARNERS` |
| `apps/api/app/writing/`, `apps/api/app/services/writing.py`, `apps/api/app/api/writing.py` | Writing (`specs/writing/`): prompts, deterministic essay analysis, `/writing/prompts`, `/essays`; the worker analyses queued essays; `services/budget.py` daily model budget |
| `data/writing/` | Writing prompts (authored, draft until reviewed), linking words by function, `error-map.yaml` (ERRANT type → hidden node, draft, with the writing observation model) |
| `apps/api/app/writing/languagetool.py`, `grammar.py`, `error_map.py`, `export_errors.py`; `apps/api/app/evalkit/writing_map.py` | Step 2.2: LanguageTool client and filter, minimal correction, ERRANT typing, mapping, evidence choice; the owner's mapping-check sheet and its score |
| `languagetool/` | LanguageTool 6.8 image (compose profile `writing`): Maven Central artifacts, every jar pinned by SHA-256 |
| `scorer/` | Band model service (compose profile `scoring`, PyTorch CPU): pinned model, revision and weights SHA-256; `POST /score` returns raw outputs only (`specs/writing/step-2.3.md`) |
| `apps/api/app/writing/scoring.py`, `scorer_client.py`; `apps/api/app/evalkit/writing_score.py`; `data/writing/scorer.yaml` | Step 2.3: calibration, band range, QWK, baselines and splits; the service client; the owner's evaluation (`develop`, then `test` once); the pin and calibration |
| `apps/api/app/writing/feedback.py`, `llm_corrections.py`, `model_calls.py` | Step 2.4: feedback with checked quotes and the disagreement rule; AI corrections (minimal, typed, never evidence); budgeted model calls with one `llm_calls` row per attempt |
| `docs/v2/writing-scorer-candidates.md` | Candidate band models read from Hugging Face: licences, data rights, loadability, the owner's choice |
| `apps/api/app/evalkit/english_gate.py`, `evals/baselines/english-placement.json` | Gate: simulated level-test accuracy on the English roadmap (gap and level), checked in CI |
| `apps/web/` | Next.js web app. English pack (`specs/web-english/`): `/` today, `/kiem-tra` level test, `/lo-trinh` roadmap, `/on-tap/{cot-moc|phan}/{slug}` milestone tests and practice, `/tu-vung` vocabulary, `/viet` writing prompts and essays, `/viet/{prompt}` editor, `/bai-viet/{id}` result, `/gioi-thieu` about (`components/english/`, `lib/english/`, Playwright tests in `e2e/`); the contest's topic research at `/kham-pha` (some steps still use sample data) |
| `apps/web/messages/` | i18n strings (`vi` default, `en`) |
| `supabase/migrations/` | Database schema (Postgres + pgvector); `0001_init.sql` = schema v1, `0002` = chunk provenance (chapter, section, kind, url), `0003` = `halfvec(1024)`, `url` → `source_uri`, HNSW dropped (rebuilt after load), `0004` = `decision_traces` (the "Vì sao?" audit trail), `0014` = `vocab_cards` + `vocab_reviews` (vocabulary state), `0015` = `level_tests`, `grammar_runs`, `grammar_answers`, `0016` = `essays` + `llm_calls.learner_id`, `0017` = `llm_calls` tokens and task + `essay_corrections` |

| `apps/api/app/research/pipeline.py` | P3 topic orchestration; optional async Retriever with explicit indexed subject, citation identity checks and original reading order; validates P1 KnowledgeGraph before publication |

| `apps/api/app/research/smoke.py` | Explicit live canonical graph/items and blind verification route smoke; preflight reads a small public book chapter without model calls |
| `specs/p3-integration/p3-follow-up.md` | P3 follow-up, validated checks, live blockers and P2/P4 integration instructions |

| `specs/p3-integration/h7-results.md` | Current P3 H7 results after main/P4 integration; audited clean library, mandatory worker retrieval, canonical schemas, model configuration, live prerequisites |
| `data/sources/p3-python-library-audit.json`, `data/sources/p3-h7-readiness.json` | Reproducible local export audit and honest environment/model-call readiness receipts |

| `data/sources/p3-python-query-label-audit.json` | Confirms all 10 P1 query label snippets in the intended book sections, with exact page URLs; no ranked retrieval or held-out tuning |
