# Tasks: Writing (phase 2)

**Owner's decisions, before 2.2 starts (new dependencies):**
- [ ] LanguageTool as a service (which image; LGPL licence, used unmodified as a separate service)
- [ ] spaCy and ERRANT in the worker (MIT licences; spaCy's small English model)
- [ ] The scorer: PyTorch CPU + transformers as a separate service; which candidate models may be tried (each model's
      and its training data's licence checked first, e.g. KevSun/IELTS_essay_scoring, the DeBERTa-v3 Task 2 scorer,
      ELLIPSE)
- [ ] The consent notice wording (Vietnamese) and how long essays are kept
- [ ] Daily limits per learner and the daily cost cap (US$)

**Owner's hands-on work:**
- [ ] Collect 50–100 essays with examiner bands for evaluation, kept in `data/private/` (never committed)
- [ ] Write the error-type → hidden-node table and check 100 mapped errors by hand
- [ ] Evaluate the candidate scorers (QWK with an interval, per-band confusion) and choose; the fine-tuning notebook
- [ ] Measure stability (5 runs per essay) and the memory of the two new services on the laptop
- [ ] Write 10 Task 2 prompts of your own; later, Task 1 chart prompts

**Build (agent), in order:**
- [ ] 2.1 prompts, submission, job, results page, consent, limits and cost cap (API built: `specs/writing/step-2.1.md`;
      web next)
- [ ] 2.2 analysis, minimal correction, ERRANT, mapping, BKT evidence
- [ ] 2.3 scorer service and the writing gate
- [ ] 2.4 feedback with verified quotes, the correction loop, rewrites, phrases to FSRS
- [ ] 2.5 Task 1
- [ ] Gate report
