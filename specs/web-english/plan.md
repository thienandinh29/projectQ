# Plan: the English pack in the web app (1.4)

Two PRs, each usable on its own.

**1.4a: level test and roadmap**
- Proxy (`app/api/backend/[...path]/route.ts`): extend the path allowlist and the forwarded query parameters
  (spec 8); tests in `lib/server-proxy.test.ts`.
- Client (`lib/english/`): types for the API's responses, hand-written decoders like `lib/decode.ts` (no new
  dependency), functions `startLevelTest`, `answerLevelTest`, `getRoadmap`, `ensureLearner`.
- Components (`components/english/`): `QuestionCard` (options, draft badge, keyboard, feedback),
  `LevelResult`, `Roadmap` (reuses `knowledge-map.tsx` and `lib/layout.ts`, milestones as nodes, tiers as columns),
  `HiddenNodes`; the existing `TracePanel` for "Vì sao?".
- Routes: `/` → English home (minimal in 1.4a: learner, level test or roadmap), `/kiem-tra` (level test),
  `/lo-trinh` (roadmap), `/kham-pha` (the contest workspace, moved, unchanged).
- Strings in `messages/vi.ts` and `messages/en.ts`.

**1.4b: practice and vocabulary**
- Client: `startMilestoneTest`, `startPractice`, `answerRun`, `vocabSession`, `vocabAnswer`.
- Components: `WordCard`, `TypedAnswer`, `RunOutcome`; routes `/on-tap` (milestone test, checks, practice) and
  `/tu-vung` (vocabulary); the full home page (spec 1); the About page (spec 6).
- Optional, if approved: `@playwright/test` with 3 end-to-end tests on the stack (level test to result; a milestone
  test that fails into checks; a vocabulary session).

**Both:** smoke checks through the proxy in `scripts/stack-smoke.sh`; `pnpm lint`, `typecheck`, `test` clean; the
web image builds in CI (the `stack` job).
