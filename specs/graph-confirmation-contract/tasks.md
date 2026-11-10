# Tasks: graph confirmation contract

- [x] P2: `GraphConfirmations` service and migration `0012`.
- [x] P3: `GET /graph/review` and `POST /graph/confirm` with the session cookie (live on `ptest2`).
- [x] P1: contract models, tests, mocks, `TEAM.md` table, spec pages aligned to P3's routes.
- [ ] P3: import the models from `app/schemas.py` instead of the local copies; bump `P1_REVISION` in
      `tests/api/test_p1_contracts.py` to a commit that has this contract (the pinned old schema is fine for the unchanged
      mocks, but the pin should move before anyone relies on the new ones).
- [ ] P5: confirm step in the main workspace (`/graph/review`, then an explicit accept to `/graph/confirm`); handle 401 and 409.
- [ ] P1: re-run step 2a of `specs/contracts/h7-run-sheet.md` through the real routes when P5 is in.
