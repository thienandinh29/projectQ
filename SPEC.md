# SPEC — NodeTrail

Positioning: *An AI tutor for any subject: knows where you are, and leads you onward.*
Target users: Vietnamese self-learners and university students; later lecturers/centers (class view).

## Problem
Median online-course completion is ~12.6% (Jordan, 2015). Self-learners don't know where to start,
forget what they learned, and chatbots answer one question at a time without knowing what to learn next.

## Core loop
Goal or syllabus upload → find trusted textbooks → build Knowledge Graph → **assess → learn → practice → adjust → review**.

## Features
1. **Knowledge Graph** — concepts + prerequisite order extracted from the textbooks. Node brightness = mastery.
2. **Adaptive placement test** — ~10 minutes to estimate the learner's level per concept.
3. **Adaptive Quiz** — items from textbook exercises; every wrong option maps to a specific misconception.
4. **Self-adjusting path** — on errors, trace the root cause back through prerequisites and remediate weak foundations.
5. **Socratic tutor** — never gives the final answer; step-by-step hints; always cites the textbook.
6. **Smart notes** — block-based notes that auto-convert into review cards.
7. **Exam prep** — review schedule planned backwards from the exam date, ~20 minutes/day.

## Engine (deterministic, testable)
- Mastery: Bayesian Knowledge Tracing per learner × concept.
- Item difficulty / learner ability: Elo.
- Spaced repetition: FSRS.
- Path selection & remediation: rule engine over the graph + mastery state.
- Grading: subject-specific objective graders (code test cases, answer keys, rubrics).
- LLM + RAG: explanations only, with citations.

### Decision audit trail (explainability)
Every engine decision returns a `DecisionTrace` next to its result, so NodeTrail can show *why* it concluded a
learner is weak at concept A and not B:
- `kind`: `bkt_update` | `placement_step` | `root_cause` | `next_item` | `review`
- `concept_slug`, `at`
- `prior`: P(L_{t-1}) before the evidence; `evidence`: item, correct/wrong, misconception, slip/guess used;
  `posterior`: P(L_t) after the evidence and the learning transition
- `rule`: which rule fired and which branch was chosen (e.g. "wrong on loops → descend to prerequisite
  boolean-expressions, lowest p_known 0.31")
- `alternatives`: the other candidates considered and why they lost

Traces are pure data (no DB inside the engine), stored per learner, returned by the API, and rendered in Vietnamese
in a "Vì sao?" panel. Existing functions (`bkt.update`, `srs.review`) stay as they are; traced wrappers add the trace.

### Verification gate (generated content)
A two-step pipeline for every generated question:
1. **Generator** writes the item and cites the `chunk_id`s it is based on.
2. **Verifier** receives **only the text of those chunks** (no other context, no answer key), tries to answer the item
   blind, and its answer is compared with the key.
The verifier is **always a different model family from the generator** (e.g. Gemini generates, Claude verifies), so a
model never grades its own output (self-preference bias).
Unanswerable or mismatched → `status = needs_review` and the item is **not served**; only `verified` items reach
learners. Tutor hints go through the same check against their cited chunks before display. Pass/fail counts feed
`guardrails/metrics.py`, next to the error rate measured on the human-labelled sample.

## Non-functional
- Vietnamese-first UI and tutor language; English secondary.
- Every explanation traceable to a source chunk.
- Learner data private by default (Supabase RLS).
- **Uploads in the demo (P1 decision, 2026-11-07):** a judge's uploaded file is read, chunked and sent to the model APIs
  (DeepSeek generates, Gemini verifies), so it leaves our servers. Allowed **for the competition demo only**, never for
  real learners, and only with a notice shown before the upload and accepted by the user (Vietnamese, in the `vi` i18n
  file): *"Tệp bạn tải lên sẽ được gửi tới dịch vụ AI bên thứ ba (DeepSeek, Gemini) để tạo lộ trình. Chỉ tải tài liệu
  công khai hoặc không chứa thông tin cá nhân. Dữ liệu demo sẽ được xóa sau buổi trình bày."* Uploaded files and the
  chunks derived from them are deleted after the demo. Before any real-learner release this needs a privacy review
  (provider data terms, consent, retention, or a self-hosted model).

## Competition demo (24-hour team build — see `TEAM.md`)
No subject is prepared in advance. A judge names **any** topic, or uploads their own file, and NodeTrail builds a
cited learning path live.

1. **Opening:** "Thầy/cô muốn học gì?" → Sena starts Deep Research (Nhanh gives a first path immediately if the
   library covers the topic, or from the uploaded file).
2. **While it researches (~3–5 min):** the team pitches the problem and solution while the screen shows Sena's
   research trail ("Đang đọc OpenStax Biology 2e — Chương 8…").
3. **The judge learns (~3 min):** graph-walk placement (~6 questions) lights up the map and locates the gap →
   wrong answer → remediation to the weak prerequisite → Socratic hint in Vietnamese with citations →
   correct answer → mastery rises, Sena praises, a review is scheduled.
4. **Dashboard:** time, cost and dropped questions for that topic (stability, real operations).
5. **Fallbacks:** Deep Research over 8 min → Nhanh for the same topic → pre-generated topic (said openly) → backup video.

Two modes and two tiers:

| | **Nhanh** (NotebookLM-style) | **Nghiên cứu sâu** (Deep Research) |
|---|---|---|
| Sources | Curated, pre-indexed open-textbook library + learner's upload (PDF, DOCX, link) | Agent searches and reads an allowlist of reputable open-education sites |
| Time | < 60 s to the graph + first placement questions (rest generated in the background) | target 3–5 min, hard cap 8 min |
| Tier / models | Free — cheap models (e.g. Gemini Flash on Vertex AI), no web search | Pro — strong models (e.g. Claude on Vertex AI/Bedrock) + web search |

Deep Research quality bar: ≥ 3 sources from ≥ 2 publishers; prerequisites follow the sources' chapter order and
learning objectives; every concept and item cited; every item passes an answerability check; licence recorded per
source, no "ND" licences. All generated content is labelled "Bản nháp tự động — chưa được giáo viên duyệt".

**Uploaded documents (agreed by the team 2026-11-07, as implemented by P4 on branch `mtri`; not yet on `ptest2`):** a learner's
uploaded document that explains the topic well enough for a small lesson is used as the source, and no external search runs, in
either mode. If it misses topics, an outline names them and they are filled from outside (Quick: the curated library; Deep: web
research). The three-sources-from-two-publishers bar applies only to external research. Everything generated is still cited to
chunks (page numbers kept for PDFs), verified, and labelled "Bản nháp tự động — chưa được giáo viên duyệt"; the demo-only upload
notice and purge above still apply. An uploaded file is recorded as "uploaded by the learner" with no licence claim.

Demo scope cuts: MCQ only (no code grading), one demo learner, no login. Kept: uploads, both modes, Free/Pro switch,
observability dashboard. Organizer expectations (Spec Kit, architecture, demo, novelty, post-contest path) are
answered in the team doc "NodeTrail — 5 định hướng theo yêu cầu Ban Tổ chức".

## Non-goals (for now)
- Gamified streaks/speed rewards.
- Generating curriculum content without a trusted source.
