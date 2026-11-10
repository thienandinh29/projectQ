# NodeTrail business baseline — current clarification

Authority: the user's latest product clarification supersedes conflicting older
demo wording in TEAM/SPEC/product-brief. This document records that clarification
for integration; it does not amend P1's frozen API/engine contracts. P4-owned code
changes stay on p4. Models, providers, database schema and migrations are unchanged.

## Purpose and scope

NodeTrail answers "where am I?", "what should I study/review next?" and "why?".
Sena accompanies one loop: goal -> placement -> map/path -> learn -> practise ->
estimate -> adjust -> review. A syllabus and a goal are two entry routes into the
same loop, not two products. Python/introductory programming is the current scope.
Golden topics are explicit test/fallback material; no claim of live source search.

Goal entry includes available time and optional exam deadline. If research is not
connected, show missing-source state or an explicitly selected sample. Syllabus/
contents supplies course structure; it is not automatically instructional evidence.
Identify concepts without supporting text before teaching/generating their questions.

A proposed map has directed prerequisites, validated references and no cycles.
Learner confirmation belongs to a learner + subject + graph revision. It is
separate from source/content verification, human content review and BKT mastery.
No fixed programming dependency graph is a universal curriculum.

Placement targets about ten minutes and estimates individual concepts; it is not
a single score. P1 remains responsible for estimation/decision rules; LLMs cannot
declare mastery, override grading or decide to skip prerequisites. A wrong choice
is evidence of a possible misconception, not a definitive diagnosis.

While practising/requesting hints, protect the final answer and progressive history.
After an accepted submission, the exercise mode may allow answer/explanation feedback.
Flashcards have questions AND answers; they are not in-progress tutor hints.
Notes are learner assertions, not verified knowledge. Support must be checked before
notes become instructional facts. Code scores must come from actual execution, with
wrong/syntax/runtime/unavailable/not-implemented states distinguished.

BKT estimates capability; deterministic rules select actions; FSRS schedules reviews;
objective graders score work; source-grounded LLMs explain. "Today" and exam priorities
may consume these outputs, but do not redefine FSRS or decay BKT with time.
20 minutes/3 tasks and slide edges are examples, not constants.

## Business -> current code -> missing -> mismatch -> owner

| Business | Existing implementation | Missing integration | Mismatch/risk and current treatment | Owner |
|---|---|---|---|---|
| Goal, time, deadline | TopicInput goal/mode/tier; ExamInput date | Unified time/deadline capture and planning flow | No fields invented; fixture captures14 days/30 minutes, no search claimed | P1/P3/P5 |
| Syllabus + supporting text | P3 upload reader; P4 graph extraction | Explicit structural/notes classification port and material matching | P4 teaching_chunks excludes caller-declared structural IDs; missing_material reports uncovered nodes; automatic classification is NOT implemented | P3/P4 |
| Proposed map + confirmation | DAG/reference checks; map API | HTTP confirmation flow/state owned by P2/P3/P5 | P4 now requires trusted confirmation callback per learner/subject/revision; default409 for placement/next/attempt/tutor. Map viewing stays available | P2/P3/P5; P4 gate |
| Content correctness | P4 blind independent item/hint gates, hashes/audits | Real model execution later | Structural validity, ready job and content verified never imply map confirmation | P4 |
| Placement | P1 graph walk <=6 answers, seed probabilities, traces | Measured duration/adaptive item difficulty confirmation | Inferences seed0.85/0.15 and are estimates; they must not be called mastered chapters | P1/P3 |
| Mastery/action rules | P1 BKT threshold0.95, path CONFIRM_BELOW0.8, prerequisite weak0.5 | Reconcile latest80% product threshold and two-attempt/skip-lecture rules | Keep current engine; do not silently substitute P4 rules or LLM judgments | P1 |
| Wrong choice/remediation | Objective MCQ grade, misconception keys, graph root-cause with mastery | Review certainty of some P1/UI wording | P4 prompts/feedback treat misconception as a signal; no fixed loops->conditions redirect | P1/P4/P5 |
| Hints versus submitted feedback | P4 hints1–3; HTTP response only correct/mastery/traces | Feedback-mode HTTP DTO and P5 display | New P4 submitted_feedback helper reveals answer only after accepted submission/current audit; not mounted as an endpoint | P3/P4/P5 |
| Sena in current lesson | Answer/misconception/history + cited source, independent verifier | Notes context provenance if notes are added | Prompt forbids free-chat drift, certainty/praise, fake code-test/mastery claims; version3 invalidates old cached hint audits | P4 |
| Wrong-answer review | Existing FSRS concept review and P2 review_cards | Persistent question/answer flashcards and notes provenance | P4 now seeds concept review on wrong answers; this is not a new flashcard DB. Q/A card is fixture-only | P1/P2/P4/P5 |
| Today/exam | P1 overdue selection, reviews/due; exam adapter503 | Unified Today tasks/time + exam prioritization | Fixture checks due review with existing engine; no20-minute/3-task hardcode, no BKT time decay | P1/P2/P3/P5 |
| Code exercise | MCQ-only P4 data; code directions deferred | Execution integration, if agreed | No fake execution, platform or new grader added | P3 |
| Frontend sample | P5 mock client explicitly simulates feedback | Browser implementation of confirmation and post-submit feedback | Mock uses arithmetic mastery,0.85 and reviews only on right: not engine truth; P5 must align once policy settled | P5/P1 |

## Corrections and integration boundary

learning.py contains internal helpers, not a second backend/queue/framework.
runtime.create_app accepts optional confirmation(learner_id, subject, graph_hash).
Only a trusted server-side record of the learner's action should answer true.
Absent callback means409. No auto-true production callback, HTTP consent field,
persistent schema or confirmation endpoint was invented. Changed maps and another
learner require confirmation again. Tutor rechecks after the awaited model work.
P2/P3 must wire the callback; a ready job alone does not enable teaching.

generate_items(..., structural_chunk_ids=...) excludes declared outline/unverified
note chunks from model evidence and rejects their item citations. Unknown IDs or
outline-only input fail before model calls. Existing callers remain compatible,
but P3 still needs to supply the classification. No keyword detector pretends to
prove document sufficiency. Remaining chunks still need answerability verification.

submitted_feedback is an internal P4 helper, never called by hint(). Its submitted
flag must come from an accepted backend submission, not a browser-provided assertion.
It requires a current item audit and uses the verifier's cited source excerpts,
not an unchecked generated explanation. P3's HTTP contract currently has no solution
field: no public solution endpoint is claimed. Do not disclose answers during exams
until the agreed mode allows them.

attempt_review reuses P1 FSRS for wrong answers, existing cards or mastered concepts.
A correct unmastered first attempt does not create a mastery claim. No FSRS formula,
BKT parameter, schema, provider, decision priority or grader changed.

## Decisions still requiring agreement

1. Product >=0.8 progression versus P1 mastery0.95; proposed middle band
   0.5 <= p <0.8 avoids overlap but is NOT silently adopted as engine policy.
2. Current path priority: open remediation -> overdue (>1h grace) -> continue ->
   learn -> confirm -> done. Product asks due reviews before new learning; clarify
   review/remediation priority, exact due boundary and grace.
3. Below50% after two attempts: consecutive? total per concept? current session?
   P1 currently may redirect immediately for weak prerequisites; its repeated
   misconception=2 is not the same as arbitrary two failed attempts.
4. Two correct answers "from the start": what session/count/reset? Skip lecture
   only, never automatically waive placement/prerequisites. No lecture state today.
5. Placement inference0.85, confidence wording, difficulty adaptation and10-minute
   target need P1 review; do not call inference certainty.
6. Confirmation UX, revision identity and revocation; HTTP feedback/assessment modes
   and authoritative accepted-submission signal need P1/P2/P3/P5 agreement.
7. Wrong-answer concept reviews are wired; persistent Q/A cards from notes, time
   estimates, Today aggregation and exam priority remain scoped follow-up decisions.

## Offline fixture and honest validation

data/golden/python-conditions/learning-loop.fixture.json labels all observations as
simulation. tests/content/learning_loop.py is a TEST driver over real P1 placement,
BKT, remediation, path and FSRS, P4 boundaries and fake gateway. Both entry modes
converge on one map/engine; outline material is reported missing. Confirmation uses
an in-memory set. Goal/deadline UI capture, hints/model review and Q/A cards are
fixtures. Feedback is helper-only, Today selection uses existing path rules, not a
new dashboard. No content is persisted or labeled genuinely model-verified.
Personal note is intentionally incorrect and remains unverified.

From apps/api, with installed dependencies:
```powershell
python -m tests.content.learning_loop
python -m pytest tests/content tests/guardrails tests/tutor tests/api tests/research tests/llm tests/uploads --no-db -q
```
No live gateway, DB probe, migration, dependency installation or provider selection
is needed for this business pass. See business-validation.json for actual results.
