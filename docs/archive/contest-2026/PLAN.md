# PLAN — build order

## Current: 24-hour team build
The contest build runs as the H0–H24 plan in `TEAM.md` (5 lanes, contracts frozen at H3, scope decision at H8,
integration run H7–H8, feature freeze at H20, moved from H18 on 2026-11-07). If this summary and `TEAM.md` disagree, `TEAM.md` wins. Milestones:

| Hour | Milestone |
|---|---|
| H3 | Repo, CI (throwaway-schema tests), schema + migration `0003` (`halfvec`), contracts + API stubs, cloud GPU VM + tunnel, bge-m3 measured, first Vertex AI call, library download started |
| H5 | Library downloaded; Bedrock reachable through the gateway |
| H7 | Pieces due at H8 merged; library indexed; first end-to-end Nhanh run |
| H8 | Nhanh mode end to end on 3 unfamiliar topics; Free/Pro models chosen; migrations `0003`–`0007` merged |
| H12 | Deep Research decision (live on stage or recording) |
| H20 | Feature freeze (moved from H18 by the lead on 2026-11-07), tag `demo-v1` |
| H23 | 3 clean rehearsals, backup video |

Already on `main` before the contest (reuse only if the organizers allow pre-contest code): schema 0001–0002,
BKT + FSRS engine, Think Python ingestion pipeline.

P1 H7 preparation (2026-11-07, local branch): engine/library handoff review in
`specs/contracts/p1-h7-review.md`; offline model screening in
`specs/model-test/offline-checks.md`. Live host/indexing, P4 cases, integrated
persistence and H7 acceptance remain pending. No checkpoint completion is implied.

P1 offline H8 tooling also scores measured verifier/latency/cost receipts via
`app/evalkit/model_metrics.py` (`specs/model-test/receipts.md`). P3's real gateway
receipts, P4's held-out cases and P1's frozen budget are still required for selection.

P1 review hardening: unique item IDs, exact cost-cap arithmetic, complete verifier
labels and deterministic default review scheduling. Algorithm flow replay is
covered in `tests/engine/test_learning_flow.py`; live H7 acceptance is still pending.

## Status against this plan (P1, 2026-11-07 about 23:25 UTC, H18; the freeze is now H20)

From a read of the pushed branches and scratch test runs, not a run on the host. `TEAM.md` has the detail and the board.

**Milestones**

| Hour | Plan | Status |
|---|---|---|
| H3 | Contracts, CI, bge-m3 measured, first model call, library download | Contracts frozen, CI green, bge-m3 measured on P2's machine (1.09 chunks/s on CPU), library downloaded and exported (8 books). The gateway uses DeepSeek and Gemini, not Vertex. |
| H7 | Pieces merged, library indexed, first end-to-end Nhanh run | Library indexed much later (3 books and 3 golden topics). Five branches are still outside the trunk. No end-to-end run. |
| H8 | Nhanh on 3 unfamiliar topics; Free/Pro models chosen | **Not reached.** Only the PDF path passed live. The model test has not run; Pro has a distinct model (`deepseek-v4-pro`). |
| H12 | Deep Research decision | Decided by the lead: Deep Research is the signature path. Its live status on the trunk is unknown. |
| H18 | Freeze, tag `demo-v1` | Freeze moved to H20. No tag yet. |
| H23 | 3 clean rehearsals, backup video | Not started. |

**`SPEC.md` features:** (1) knowledge graph: built, live evidence on the PDF path; (2) placement and (4) remediation: engine done and unit-tested, not yet shown live through the routes; (3) adaptive quiz with a misconception per wrong option: 7 verified questions on the PDF path; (5) Socratic tutor: 3 verified hints with citations live; (6) smart notes: not built; (7) exam prep: a route exists, handover missing.

**Engine:** BKT, FSRS, rule engine, traces, MCQ grading and the verification gate exist. **Elo does not exist.** The verifier's catch rate has not been measured.

**Demo steps:** (1) Deep Research opening: unproven on the trunk; (2) research trail screen: exists; (3) placement, wrong answer, remediation, hint, mastery: not shown live; (4) dashboard: no data source until `TopicMetrics`, no route or panel yet; (5) fallbacks: the Deep-to-Nhanh switch at 8 minutes is unconfirmed, no backup video.

**Decisions that changed:** hosting is P2's own machine, not a cloud VM and tunnel (the repo has a compose file for the database and TEI, no Dockerfile or Vercel config); models are DeepSeek generating and Gemini verifying (see "Model decision" in `TEAM.md`); the freeze is H20; structlog and Langfuse are not in the app code, so cost has no source. The "Decisions made" list below predates these changes.

**Measurements promised and not made:** the H8 model test; the 50-item and 20-hint human labelling (`data/guardrails/human_labels.template.jsonl` is still a template); the tutor evaluation of at least 18 of 20; retrieval hit rate on the indexed library (`data/eval/think-python-2e.yaml` is ready).

**Proposed cuts, not yet agreed by the lead:** smart notes, exam prep, Elo, structlog and Langfuse (replaced by `TopicMetrics` fed from the gateway's per-attempt telemetry), the cloud VM and Vercel hosting for the demo, and the curriculum and class features (`p5-curriculum-class`). For measurements, a smaller labelled sample (for example 20 items and 10 hints) is the realistic target. Until the lead confirms, the original plan stands.

## After the contest
| When | Goal |
|---|---|
| Months 1–2 | Pilot with one real class; login; move the API to an always-on host |
| Months 3–4 | Launch Free + Pro; lecturer class view |
| Months 5–9 | More subjects, learning-gain study, partnerships with centers and universities |

## Long-term phases (reference)
Each phase should be finished properly (tests, docs) before the next. Estimates assume ~20 h/week solo.

| # | Phase | Key deliverables | Status |
|---|---|---|---|
| 0 | Harness | CLAUDE.md, MAP, SPEC, PLAN, git, env | done |
| 1 | Scaffolding | Monorepo, `apps/api` (FastAPI + uv), `apps/web` (Next.js), Supabase local, CI lint/test | todo |
| 2 | Data model | Schema: users, subjects, sources, chunks, concepts, edges, items, misconceptions, attempts, mastery, cards | todo |
| 3 | Learning Engine | BKT, Elo, FSRS, rule engine as pure tested modules | todo |
| 4 | Ingestion + RAG | Textbook ingest → chunks → embeddings (pgvector) → cited retrieval; LLM gateway | todo |
| 5 | Knowledge Graph builder | Extract concepts + prerequisites from sources; graph review tools | todo |
| 6 | Assessment | Placement test, adaptive quiz, misconception-tagged distractors, graders | todo |
| 7 | Adaptive path | Root-cause remediation over the graph | todo |
| 8 | Socratic tutor | Hint ladder, citations, no direct answers | todo |
| 9 | Frontend | Sena UI, graph view, quiz, tutor chat, vi/en i18n | todo |
| 10 | Notes + review | Block notes → cards, FSRS review, exam backward scheduler | todo |
| 11 | Class view | Lecturer dashboards, class weak spots | todo |

## Decisions made
- Demo: the judge's own topic or uploaded file; no pre-built subject. MCQ only.
- Web: Next.js on Vercel. API: FastAPI in Docker on a Google Cloud GPU VM in Singapore (AWS backup VM, roles swappable), via a named Cloudflare Tunnel; organizer cloud credits, open at H0 (GPU or CPU decided by H1).
- Data: Supabase (Postgres + pgvector `halfvec`, Storage), ~30k-chunk budget. Jobs: Postgres `topic_jobs` queue + worker service (Redis after the contest).
- Embeddings: BAAI/bge-m3, 1024 dims, served by a TEI container on the API VM (GPU or CPU image); bulk indexing with the same image on a temporary GPU VM.
- LLM model roles: long-context Gemini on Vertex for graph extraction; verifier always a different model family from the generator (e.g. Claude on Bedrock); Pro tutor on Claude, confirmed at H8.
- LLM: gateway with Vertex AI primary, Bedrock and OpenRouter fallbacks; per-tier routing (Free = cheap models, Pro = strong models).
- Planning: GitHub Spec Kit for every lane (examiner's request), one page per document, constitution from `CLAUDE.md`. CI: pytest + ruff required, mypy warn-only.
- Frontend agent reads designs through MCP (Figma, shadcn, browser), configured locally per person.

## Open decisions
- Licensing beyond the demo: Think Python text is CC BY-NC-SA 4.0 — fine for a non-commercial demo,
  but any commercial NodeTrail needs another source or permission, and material derived from the text
  (e.g. generated quiz items) must keep attribution and the same license.
