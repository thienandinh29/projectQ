# Tasks: Writing (phase 2)

**Owner's decisions, before 2.2 starts (new dependencies):**
- [x] LanguageTool as a service (LGPL, unmodified, own container): our own image, pinned (approved 14 Nov; built
      from LanguageTool's Maven Central artifacts, every jar pinned by SHA-256)
- [x] spaCy and ERRANT in the worker (MIT licences; spaCy's small English model) (approved 14 Nov)
- [x] (approved 14 Nov) The writing observation model (proposed slip 0.3, guess 0.4, no transit) and the draft rule: mapped errors move
      mastery only for `DRAFT_ITEM_LEARNERS` until the 100-error check reaches 90%
- [ ] The scorer: PyTorch CPU + transformers as a separate service; which candidate models may be tried (each model's
      and its training data's licence checked first, e.g. KevSun/IELTS_essay_scoring, the DeBERTa-v3 Task 2 scorer,
      ELLIPSE)
- [ ] The consent notice wording (Vietnamese) and how long essays are kept (a draft is in `apps/web/messages/vi.ts`,
      `english.writing.consent`, version `writing-v1`; changing it means a new version in the API and the web app)
- [ ] Daily limits per learner and the daily cost cap (US$)

**Owner's hands-on work:**
- [ ] Collect 50–100 essays with examiner bands for evaluation, kept in `data/private/` (never committed)
- [ ] Review the error-type → hidden-node table (`data/writing/error-map.yaml`, starter rows in step-2.2.md) and check
      100 mapped errors by hand (`app.writing.export_errors`, then `app.evalkit.writing_map`); add hidden nodes for
      prepositions, word form and word order to raise coverage
- [ ] Recall: in 10 of your own essays, mark the errors LanguageTool missed (it misses many agreement errors in
      mid-sentence; `step-2.2.md`, Measured)
- [ ] Evaluate the candidate scorers (QWK with an interval, per-band confusion) and choose; the fine-tuning notebook
- [ ] Measure stability (5 runs per essay) and the memory of the two new services on the laptop
- [ ] Write 10 Task 2 prompts of your own; later, Task 1 chart prompts

**Build (agent), in order:**
- [x] 2.1 prompts, submission, job, results page, consent, limits and cost cap (`specs/writing/step-2.1.md`)
- [x] 2.2 analysis, minimal correction, ERRANT, mapping, BKT evidence (spec: `specs/writing/step-2.2.md`)
- [ ] 2.3 scorer service and the writing gate
- [ ] 2.4 feedback with verified quotes, the correction loop, rewrites, phrases to FSRS
- [ ] 2.5 Task 1
- [ ] Gate report
