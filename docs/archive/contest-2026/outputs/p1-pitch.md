# P1 pitch section: the engine (about 45 seconds)

Spoken lines are Vietnamese. Notes are English. Every claim below is backed by something in the repo; the last section lists what **not** to say.

## The three sentences (Vietnamese)

1. **Bộ máy quyết định, AI chỉ giải thích.** "NodeTrail không để AI tự quyết định bạn học gì tiếp: một bộ máy học tập xác định đo mức nắm vững từng khái niệm bằng Bayesian Knowledge Tracing, tìm gốc rễ lỗ hổng trên đồ thị tiên quyết, và lên lịch ôn bằng FSRS; mô hình ngôn ngữ chỉ giải thích, và luôn kèm trích dẫn giáo trình."
2. **Sai ở đâu, quay lại đúng chỗ đó, và nói rõ vì sao.** "Khi bạn trả lời sai, hệ thống truy ngược theo đồ thị đến khái niệm nền yếu nhất, cho bạn học lại rồi đưa bạn về đúng chỗ vừa vấp, và bảng «Vì sao?» giải thích bằng tiếng Việt: xét khái niệm nào, mức nắm hiện là bao nhiêu, và những lựa chọn khác bị loại vì sao."
3. **Khen đúng lúc, và không hiển thị câu chưa được kiểm chứng.** "Sena chỉ khen khi bạn thực sự hiểu, không khen vì nhanh hay vì chuỗi ngày; và mọi câu hỏi do AI tạo phải được một mô hình khác họ kiểm chứng trên chính đoạn giáo trình đã trích, câu nào chưa qua thì không bao giờ đến tay người học."

## What to point at on the screen

| While saying | Point at | Where it comes from |
|---|---|---|
| Sentence 1 | The map brightening after placement (node brightness is mastery) | `GET /graph`, engine `placement.seed_mastery` |
| Sentence 2 | The "Vì sao?" panel right after a wrong answer, reading out its Vietnamese reason | `DecisionTrace.rule_vi`, written by `engine/remediation.py` and `engine/graph.py` |
| Sentence 2 | The remediation prompt, then the learner returning to the concept they failed on | `remediation.remediate`, `remediation.resume` |
| Sentence 3 | The source link on a hint or question (page number for a PDF) and the "Bản nháp tự động — chưa được giáo viên duyệt" label | Citations from retrieval; the draft label from `SPEC.md` |

The panel text has the shape "Sai ở vòng lặp → kiểm tra nền tảng biểu thức boolean (p_known thấp nhất 0,31)" (see `specs/contracts/mocks/attempts.wrong.json`, built from real engine output). The live wording depends on the run, so read what is on screen, not this line.

## Likely questions, with answers that are true today

- **"Why not just ask the LLM what to learn next?"** The decision has to be repeatable, testable and explainable. The engine is pure code with unit tests, and every decision returns a trace the learner can read. The LLM never chooses the next step.
- **"How accurate is the placement?"** Say: it estimates the level in about six questions and shows its reasoning. On simulated slip and guess noise the exact-gap hit rate is 56–64%, below our 90% target, which is not waived; the next step is calibrating on real learners. Do not give a headline number.
- **"What stops the AI making up a question?"** A different model family checks each question blind against the cited textbook passages, and a question that does not pass is not served. We have **not yet measured** how many planted errors the verifier catches, so do not quote a catch rate.

## Do not say (not shown or not measured)

- Any placement accuracy figure, or "10 minutes" (the demo placement is about six questions).
- Any verifier catch rate or "zero hallucinations" (the planted-error test is unrun).
- A learning-gain claim (nothing has measured one).
- That mastery numbers are exact: they are model estimates and the panel shows them as such.
- Anything about Sena's praise rules unless the screen shows it: check before the demo that praise lines appear only when a concept reaches mastery, and never for speed or streaks.

## Check before the demo (P1)

1. Run steps 3 to 9 of `specs/contracts/h7-run-sheet.md` live once; the engine's panel and remediation have not yet been shown through the real routes.
2. Read the panel text on the actual run and fix any line that is stiff or wrong in Vietnamese.
3. Confirm the draft label is visible on every screen that shows generated content.
