# Spec: code exercises graded in a sandbox (Milestone A, step 1)

**Problem.** The Python course is practised only with multiple choice, so NodeTrail never sees a learner write code.
Code objectives already declare test cases (`data/courses/python-basics.yaml`), but nothing runs them. Running learner
code is the riskiest thing the system would do: it is untrusted input that executes.

**Goal.** A learner writes a function for a `code` objective; the system runs it against the objective's tests in
an isolated sandbox, grades it deterministically, updates BKT from the result, and the tutor can explain failures
without writing the solution.

## Behaviour
1. **Item.** A code item has a Vietnamese prompt, a function signature and starter code, **visible tests** (shown to
   the learner) and **hidden tests** (never sent to the browser or the sandbox output), a reference solution and
   at least one known-wrong solution, all cited to source chunks like any item.
2. **Isolation.** Learner code never runs in the API or worker process. It runs in a separate, throwaway sandbox
   with: no network; a read-only file system except a small temporary directory; a non-root user; no environment
   secrets; limits on wall time (5 s), CPU time, memory (256 MB), processes (32) and output size (64 KB).
   Exceeding a limit ends the run and is reported as such, not as a crash of the system.
3. **Grading.** For each test the sandbox returns only the `repr` of the value the learner's code produced (or the
   exception type and message, truncated). The **comparison with the expected value happens outside the sandbox**, so
   learner code cannot forge a pass by printing results, and hidden expected values never enter the sandbox.
4. **Result.** `score` = share of tests passed (visible and hidden). BKT receives *correct* only when every test
   passes, unaided-ness follows the mastery gate (`specs/mastery-gate/`), and hints used weaken the evidence as for
   MCQ. The learner sees per-test results for visible tests, and only a count for hidden ones.
5. **Feedback.** The tutor explains a failing visible test from the test, the actual output and the cited chunks.
   It never returns a complete solution: a deterministic check refuses any hint that defines the target function or
   contains more than a few lines of code.
6. **Limits on submissions.** Code size at most 20 KB; at most 30 runs per learner per minute; each run recorded
   (code, results, limits hit) in `attempts.answer`.
7. **Self-test.** Every code objective's reference solution must pass all tests and every known-wrong solution must
   fail at least one, checked in CI. A course whose tests cannot tell right from wrong is refused.
8. **Escape tests in CI.** Attempts to open a network connection, write outside the temporary directory, read
   environment variables or files outside the sandbox, fork without limit, allocate unbounded memory, loop forever,
   print without limit, and import `os` to run commands must all end safely with the right limit or error.

## Success criteria
- All escape tests pass on the runner image; no learner code runs in the API process (asserted by a test).
- Grading is deterministic: the same code gives the same result on repeated runs.
- p95 grading latency under 3 s for the Python course's objectives on the reference machine (measured, reported).
- The Python course's code objectives work end to end through the API.

## Out of scope (this spec)
Languages other than Python; running code in the browser (Pyodide) for instant feedback; partial-credit BKT
(fractional evidence); plagiarism detection; the web editor component (next spec, needs a dependency decision).

## Decisions needed from the owner
1. **Isolation technology** (see `plan.md`): Docker container per run (recommended), with gVisor as an optional
   hardened runtime, versus nsjail or a hosted sandbox service.
2. **Hidden tests:** at least one per objective (recommended) to discourage hard-coding the visible answers.
3. **Limits:** the defaults above (5 s, 256 MB, 32 processes, 64 KB output, 30 runs per minute).
