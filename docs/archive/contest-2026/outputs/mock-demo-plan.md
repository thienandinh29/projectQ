# Mock demo plan (P1 runs it; the lanes keep building)

Purpose: one rehearsal of the real demo, run exactly as it will be on the day, so the failures show up now. Source: `SPEC.md` demo steps 1 to 5, `specs/contracts/h7-run-sheet.md`, `outputs/p1-pitch.md`. Times are targets from the spec or measured once; none is a promise.

Fill in: **mock at `[time]`, real demo at `[time]`**. After the freeze (H20) only bug fixes go in.

## 1. Script and timing (about 10 minutes)

| Min | What happens | Who | Notes |
|---|---|---|---|
| 0:00 | "Thầy/cô muốn học gì?" The judge names a topic or hands over a file. | P1 | Have a Python request and a PDF ready if the judge has none. |
| 0:20 | Sena starts. The research-trail screen runs while the team talks. | P2 runs the screen | Deep Research target is 3 to 5 minutes, hard cap 8. A PDF measured 163 s once, including a retry. |
| 0:30 to 4:00 | Pitch: the problem, the solution, the engine. | P1 (45 s from `p1-pitch.md`), P5 or P4 for the rest | Cover the verification gate and the upload notice here. |
| 4:00 | The graph appears. The learner reads it and presses accept. | P5 | The accept step is required: practice returns 409 until it's done. |
| 4:30 | Placement, about 6 questions. The map lights up and the gap shows. | Judge answers, P1 narrates | Make sure one answer is wrong, on purpose, so remediation shows. |
| 6:00 | Wrong answer: remediation to the weak prerequisite, then a hint with citations. | P1 reads the "Vì sao?" panel aloud | Open one source link to show the page. |
| 7:30 | Correct answer: mastery rises, Sena praises, a review is scheduled. | P5 | Praise only for mastery, never for speed. |
| 8:30 | Dashboard: time, dropped questions, cost (shows "chưa rõ" if unknown). | P2 | Only if the dashboard exists by the freeze; otherwise skip and say nothing. |
| 9:00 | Questions. | P1 leads, others answer their own area | See section 4. |

## 2. Roles on the day

| Role | Person | Watches |
|---|---|---|
| Lead and narrator | P1 | The clock and the fallback triggers; reads the panel |
| Operator | P2 | Host, API, worker, embeddings service, the cached topics; switches the fallback |
| Pipeline watcher | P3 | The research trail for failures; the model quota |
| Content and verifier | P4 | How many questions were verified or dropped; answers questions on the gate |
| Screen and Sena | P5 | The UI, the accept step, the recording |

## 3. Pre-flight (do each, tick as you go)

**An hour before**
- [ ] Trunk head named and CI green; the same head is what runs on the host.
- [ ] Health check shows the database ok; the embedding service answers; the API and worker are up.
- [ ] New (rotated) keys in the host `.env`; a live smoke call to both providers passes; the Gemini key has quota (a free key allows 20 requests a day).
- [ ] Warm topics already built and cached: Python plus two or three others the judges are likely to name. Only Python, Logic and Statistics are indexed in the library, so say "any topic" only for Deep Research and uploads.
- [ ] A verified Python topic exists (6 or more verified items across 3 or more concepts).
- [ ] The upload notice shows and needs a tick; the purge removes an upload afterwards.
- [ ] Screen recording tested; a backup video exists from a clean run.

**Five minutes before**
- [ ] Browser zoom, full screen, notifications off, a second window ready on the cached topic.
- [ ] Network is stable; a phone hotspot is ready.

## 4. Fallback rules (decide on the clock, not by feel)

| Trigger | Do |
|---|---|
| Deep Research passes 8:00 or reports it cannot find 3 sources from 2 publishers | Switch to Nhanh for the same topic and say so |
| Nhanh does not show the graph and first questions quickly (spec target: under 60 s) | Open the cached topic and say it is pre-generated |
| The model API is down or out of quota | Same: cached topic, said openly |
| Anything else stuck for 30 seconds | Play the backup video; do not debug on stage |

## 5. Questions judges may ask, with answers that are true today

- **Why not just ask an LLM what to learn next?** The decision must be repeatable, testable and explainable. BKT, graph rules and FSRS decide; the LLM explains with citations. The same answers give the same path and the same reason.
- **How accurate is the placement?** It estimates level in about six questions and shows its reasoning. On simulated slip and guess noise the exact-gap rate is 56 to 64%, below our 90% target, which is not waived. Calibrating on real learners is the next step. No headline number.
- **What stops invented questions?** A model from a different family answers each question blind from the cited passages. A question that does not match the key is not served. We have not yet measured how many planted errors it catches.
- **What happens to an uploaded file?** The notice appears first; demo only; the file and its chunks are deleted afterwards.
- **Where do the sources come from, and what are the licences?** A curated open-textbook library and an allowlist of open-education sites; the licence is recorded per source, and "no derivatives" licences are excluded. The Think Python text is non-commercial.
- **What does it cost?** The dashboard shows measured cost, or says it is unknown. Do not give an estimate.
- **How is this different from NotebookLM or ChatGPT's study mode?** Say "in the products we checked": those are quiz and tutoring styles on your sources; ALEKS decides with a model but over fixed expert content. We build the content live from trusted sources and decide with an engine whose reasons you can read.
- **Does it work for any subject?** Deep Research and uploads are meant for any topic. The pre-indexed library covers Python, logic and statistics.
- **What next?** A pilot with one class, login, an always-on host, then more subjects (`PLAN.md`).

## 6. Do not say
A placement accuracy number, a verifier catch rate, "no hallucinations", a learning-gain claim, "10 minutes" for placement, or anything about a competitor lacking a feature unless a source says so. Do not claim Deep Research works for a topic you have not run.

## 7. During and after the mock
- P1 keeps a log: time of each step, every failure, every judge question.
- Within 30 minutes: a short retro. Each failure gets one owner and a fix, or a cut. Only bug fixes after the freeze.
- Re-run the failed step once to tell a flake from a real fault.
- Update this file with what changed.

## 8. What I need each lane to confirm before the mock
P2: the host health and the cached topics. P3: Deep Research on the trunk, one live run. P4: the verified Python items and the count of dropped questions. P5: the accept step, the next-item loop and the recording. Ask each for one line.
