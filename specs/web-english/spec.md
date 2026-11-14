# Spec: the English pack in the web app (step 1.4 of `docs/v2/plan-english-pack.md`)

The learner uses everything built in 1.1–1.3a in the browser, on a laptop or a phone, on real data only. This is the
step that lets the owner study with NodeTrail every day, which is part of the phase 1 gate.

## Screens
1. **Home ("Hôm nay").** Sena greets the learner and shows today's work: vocabulary due and new words left, the next
   milestone, what to learn next (with "Vì sao?"), and a button to take the level test when there is no result yet.
   No streaks, no speed rewards: Sena praises only mastery (project rule).
2. **Level test.** One question at a time: prompt, 3–4 options, a "Bản nháp" badge on draft items, and progress as
   "Câu 7" (the test is adaptive, so no fixed total), then the vocabulary part. The result screen shows the
   grammar and vocabulary levels and the IELTS range exactly as the API words it ("ước lượng, không phải điểm IELTS"),
   the milestones found known, and where to start. The learner may pick a target (B2 or C1) before starting.
3. **Roadmap ("Lộ trình").** Milestones grouped by CEFR level in learning order, as sections (changed 14 Nov from the
   React Flow map: a draggable graph is hard to use on a 390 px phone; a graph view can come back later for laptops).
   Colour and a text label show the status (known, mastered, cần ôn, chưa học), never colour alone. Hidden nodes
   appear under a milestone only when it is partial or the learner opens it, each with its p_known as a bar. The next
   milestone and "learn next" are highlighted; every decision opens the existing "Vì sao?" panel.
4. **Milestone test, quick checks, practice.** The same question card. After each answer: right or wrong, the right
   answer, and for a wrong answer the misconception in plain Vietnamese (the run answer returns `feedback`; the
   explanations live in `data/items/misconceptions.vi.yaml`, draft, one per misconception id, checked in CI). At the end: the outcome (pass, pass
   with a gap, fail), the quick checks starting straight away when the API returns them, and what to learn next.
5. **Vocabulary ("Từ vựng").** The daily session: a new word is shown first as a card (word, part of speech, level,
   definition, Vietnamese gloss, example), then asked. Multiple choice as buttons; typed answers in a text field with
   the first-letter hint. Feedback shows the accepted answer when wrong, the word card, and when it comes back.
6. **About ("Về bản trải nghiệm").** Shows the learner id with a copy button (the owner puts it in
   `DRAFT_ITEM_LEARNERS`) and states that levels are estimates and items may be drafts.

## Behaviour
7. **Real data only.** The screens call the API through the existing server-side proxy; the API key never reaches the
   browser. Mock data exists only for unit tests and is never shown as real (project rule). If the API is
   unreachable, the screen says so in Vietnamese and offers a retry; nothing is invented.
8. **The proxy allows exactly the new routes** (`level-tests`, `level-tests/{id}/answers`, `roadmap`,
   `milestones/{slug}/tests`, `nodes/{slug}/practice`, `grammar-runs/{id}/answers`, `vocab/session`,
   `vocab/answers`) and the query parameters they need (`course`, `list`, `limit`, `new_limit`, `max_level`), with
   the same rules as today: same-origin POST only, no `..` or encoded separators, ids checked by pattern.
9. **One learner per browser.** The learner is created once (`POST /learners`) and remembered (the proxy's existing
   learner cookie, plus the id for display). No login in this phase.
10. **Phone first.** Usable on a 360 px wide screen; options are large buttons; keys 1–4 choose an option and Enter
    submits (laptop); the typed field opens the phone keyboard without auto-correct or auto-capitalisation.
11. **Vietnamese UI**, English secondary, every string in `messages/vi.ts` and `messages/en.ts`. English content
    (prompts, words) stays English.
12. **The contest topic-research screens stay** reachable from the navigation but are no longer the home page.

## Acceptance
13. Unit tests (Vitest) for the API client and decoders, the proxy allowlist (new paths and parameters allowed,
    anything else refused), and screen logic (status labels, progress, feedback text).
14. The stack smoke test drives the new routes through the web proxy (not only the API).
15. The owner takes the level test and studies daily from the browser; the phase 1 gate counts 2 weeks of that.

## Decisions for the owner
- **Decided (owner, 14 Nov):** the English pack is the home page; topic research moves to `/kham-pha`.
- **Decided (owner, 14 Nov):** `@playwright/test` is added as a dev dependency in 1.4b for browser end-to-end tests.

## Not in scope
Accounts and login, Writing, audio, offline use, a separate mobile app.
