# Tasks: Remediation rules

- [x] T1 `WEAK_THRESHOLD`, `root_cause` default fixed; wording for a solid-but-unmastered prerequisite; tests
- [x] T2 `remediation.remediate`, `RemediationPlan.to_contract`, `resume`
- [x] T3 Property tests on 45 shapes; placement-seeded scenario; misconception cases
- [x] T4 `attempts.wrong` mock built from `remediate`
- [ ] T5 P3 wires `remediate` into `POST /attempts` and `resume` into `GET /next-item` (handoff board)
- [ ] T6 Tune `WEAK_THRESHOLD` and `REPEATED_MISCONCEPTION` from the H8 end-to-end runs
