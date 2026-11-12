# Spec addendum: code practice through the API (plan week 1)

**Why a separate route.** `POST /attempts` is built around multiple choice: `answer` is a strict option index and
items come from the verified-item pipeline. Code answers are text, are graded by the runner, and come from authored
course specs. Changing the MCQ contract would touch both backends and the web app; a separate route keeps the MCQ
contract unchanged.

## Routes (mounted only when `RUNNER_URL` is set)
- `GET /code/exercise?learner_id&course&objective` → the public exercise: function name, Vietnamese prompt, starter
  code, visible tests (call and expected value), number of hidden tests. Never the reference, wrong solutions or
  hidden tests.
- `POST /code/attempts` `{learner_id, course, objective, code, hints_used}` → runs the code in the sandbox, grades it,
  updates BKT and returns `{status, score, correct, visible[], hidden_passed, hidden_total, message_vi, p_known,
  mastered, traces}`.

## Behaviour
1. The course spec is the source of truth. On first use the API syncs it into the database (subject, concepts and
   prerequisite edges declared in the course, one `items` row per code objective with `kind='code'`). Sync is
   idempotent.
2. The sandbox run happens **outside** the database transaction; the learner's state is updated in one transaction
   afterwards.
3. BKT uses the `code` parameters (guess 0.05), weakened by hints (`params_with_help`); `correct` means every test
   passed; confirmed mastery follows the mastery gate. A run stopped for time, memory or output counts as an incorrect
   attempt. A runner that cannot be reached is a 503 and records nothing.
4. Limits: code at most 20 KB; at most 30 code attempts per learner per minute (429 beyond).
5. Each attempt stores the code, `hints_used`, status, score and per-test results in `attempts.answer`, plus the BKT
   (and review, when mastered) traces.
6. Code items are authored and self-tested in CI; they are stored with status `needs_review` because the database
   requires cited chunks for `verified`. Citing the source chunks is a later step.
7. **Code hint guard:** `tutor/code_hints.code_hint_leak` refuses a hint that defines the target function, contains
   a line of the reference solution, or has more than 3 lines of code. The LLM-written code hint itself needs model
   keys and comes later.

## Not in this addendum
Web editor (week 4), the LLM code tutor, placement over code items, the map-confirmation gate (course subjects are
authored, not generated).
