# H7 end-to-end run sheet (P1 leads, everyone fixes)

Window: H7–H8. Goal: one learner goes topic → graph and items → placement → wrong answer → remediation → resume →
correct answer → review card, **through the real HTTP routes, real models and real retrieval**. Source: the acceptance
sequence in `specs/contracts/p1-h7-review.md`; route shapes in `TEAM.md` (Contracts). Nothing in this sheet claims a
result: fill the record at the bottom as you go.

## 0. Which run counts for the demo (added at about H17.5)

Run the 12 steps below once per path; the record table is per path, so copy it. Status from the branches as pushed, not from a run of mine.

| Path | Status | Use in the demo |
|---|---|---|
| **A. Quick mode, "tôi muốn học Python", from the indexed library** | **No live run recorded yet.** The fallback if Deep Research stalls, and the quickest path to verify. | Run first. |
| **B. Uploaded PDF** | **Passed live** per P4's `outputs/live-lesson-acceptance.md` on branch `mtri`: 162.7 s including one retry, 4 chunks embedded, graph confirmed in the UI, 7 verified questions, 9 answers graded, 3 verified hints with citations. Placement, remediation, resume, mastery and the review card are **not** reported there; steps 3 to 9 still need a pass. | Second path; also the cheapest backup video: record it. |
| **C. Deep Research, "tôi muốn học Python"** | **Failed live on P4's `mtri` branch** (no 3 eligible sources from 2 publishers, 91 s), which lacks 7 `ptest2` commits including the overnight research-discovery fixes. **Unknown on the `ptest2` head.** | **The signature path** (`SPEC.md` opening). Run right after A; at the 8-minute cap fall back to Nhanh for the same topic. |

## 1. Go / no-go (check before anyone starts; any "no" = fix it first or run the fallback)

| # | Condition | Owner | Go? |
|---|---|---|---|
| 1 | Trunk (`ptest2`) has `main` and `p4` merged; CI green on the trunk head | P2, P4 | |
| 2 | `/next-item` skips answered items and never dead-ends (review finding 2) | P2 | |
| 3 | Web client has `nextItem`, proxy allows `next-item` (finding 3), or the run uses the API directly | P5 | |
| 4 | Migrations `0003`–`0008` applied; `decision_traces` exists | P2 | |
| 5 | TEI up; index holds `think-python-2e` (+ the two other books if ready); a Vietnamese query returns the right section in about 1 s | P2 | |
| 6 | New (rotated) DeepSeek and Gemini keys in the host `.env`; `python -m app.llm.smoke --live` passes for both | P2, P3 | |
| 7 | API key set (non-empty `API_KEY`) and the client sends it | P2 | |
| 8 | Research pipeline built **with a retriever and subject** (otherwise citation checks are skipped) | P3 | |
| 9 | At least one verified topic (Python) with ≥ 6 verified items across ≥ 3 concepts incl. one prerequisite chain | P4 | |
| 10 | The learner can confirm the knowledge map over HTTP and in the UI (the backend returns 409 for practice, attempts and hints until the map is confirmed, tied to learner, subject and graph revision; added after P2's local run, 2026-11-07) | P2, P3, P5 | |

Not met by the start of H8 → whole team on Nhanh with the golden/pre-generated topic; Deep Research stays a bonus.

## 2. Steps (one demo learner, topic "Tôi muốn học Python")

Each step: do it, read the expected result, write what happened in the record (step 2a has no row of its own; note it on step 2's row). Use `$API` for the base URL.

| Step | Action | Expect | Owner reads |
|---|---|---|---|
| 1 | `POST /topics` `{goal_vi, mode: "quick", tier: "free"}`; poll `GET /topics/{id}` (or `/events`) | job reaches `done`; graph and ≥ 6 verified items stored; every concept and item cites chunks; `needs_review` items are not served | P3, P4 |
| 2 | `GET /graph?learner_id=&subject=` | DAG with no cycle; prerequisites follow the book's chapter order; node `p_known` all at the unseen prior | P1 |
| 2a | **Confirm the map as the learner** (route or UI control named by P2, P3 and P5; the confirmation is tied to learner, subject and graph revision) | before confirming, practice, attempts and hints return **409**; after confirming they succeed; confirming changes no mastery. Never bypass the check in production to get a test through. | P2, P5 |
| 3 | `POST /placement/next` repeatedly, answering mostly right, then one concept wrong | at most 6 questions; `done: true` with `gap_slug`; **mastery seeded once** (known ≈ 0.85, unknown ≈ 0.15); each response carries a `DecisionTrace` | P1 |
| 4 | `GET /next-item` | an unserved verified item of the concept `next_step` chose, near its target difficulty; `reason_vi` in Vietnamese | P1, P2 |
| 5 | `POST /attempts` with a **wrong** option (misconception-tagged) | `correct: false`, `misconception_vi`, lower `p_known`; if a prerequisite is weak (< 0.5) a `remediation` pointing at the weakest one; traces stored with the attempt | P1 |
| 6 | Re-read state from a **fresh connection** | attempt, mastery, review card and traces all persisted (one transaction) | P2 |
| 7 | `POST /tutor/hint` (levels 1–3) | Vietnamese hint with citations, never the answer; hint passed the verifier | P4 |
| 8 | Answer the prerequisite correctly until mastered, then `GET /next-item` | resumes the origin concept; `rule_vi` says why | P1 |
| 9 | `POST /attempts` correct on the origin concept | `p_known` rises; `mastered` flips at 0.95; a review card exists; `GET /reviews/due` lists it (due now; the path ignores cards less than 1 h overdue) | P1 |
| 10 | Replay step 5 with the **same request twice** | no duplicate attempt and no second BKT update (finding 5); an out-of-range answer index writes nothing | P2 |
| 11 | Kill the worker mid-job, restart | the job is retried or fails visibly, no duplicate topic data | P2 |
| 12 | Open the web app on the same learner | map brightness matches step 9; "Vì sao?" shows the Vietnamese `rule_vi` | P5 |

## 3. What to record (one line per step)

`step | pass/fail | wall time | tokens in/out and cost (Langfuse or gateway attempts) | items dropped by the verifier | note`.
Keep the successful attempt's latency apart from retries (gateway telemetry has both). Nhanh target: graph and first
placement questions in under 60 s (SPEC).

## 4. Rules for the room

- P1 calls pass or fail on engine results; P2 on persistence; P3 on routes and retrieval; P4 on content and verifier; P5 on
  the screen. One failing step gets one owner and a one-line cause before the next step.
- A step fails if it needed a hand edit in the database or a restart nobody can explain. Write that down; do not patch around it.
- No threshold, placement setting or public accuracy number changes during the run. Placement exact-gap accuracy under
  noise is 56–64% (target ≥ 90% unmet, not waived); say so if asked.
- Uploads: only with the notice accepted (`SPEC.md`), and delete the upload and its chunks afterwards.
- Never paste keys into chat or the record.

## 5. After the run

P1 writes the result (steps passed, failed, times, cost) into the board and decides: H8 checkpoint (3 unfamiliar topics),
which models Free and Pro use (from the Vietnamese test), and whether the reranker is needed (needs P4's ≥ 20 labelled
questions for recall@5, target 0.8).

## Record

| Step | Result | Time | Cost / tokens | Dropped | Note |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |
| 9 | | | | | |
| 10 | | | | | |
| 11 | | | | | |
| 12 | | | | | |
