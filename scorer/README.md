# Scorer service

The writing band model (`specs/writing/step-2.3.md`): `POST /score {text}` returns the model's **raw** outputs; the API
calibrates them to a band range (`apps/api/app/writing/scoring.py`). It never shows a number by itself.

- Model: `JacobLinCool/IELTS_essay_scoring_safetensors` at commit `8d8d0193…`, weights SHA-256 `3c587f43…` (MIT; training
  data provenance unknown, see `docs/v2/writing-scorer-candidates.md`). Pinned in `docker-compose.yml`; the service
  refuses to start without a full commit hash or when the weights do not match.
- Start: `docker compose --profile scoring up -d scorer`, and set `SCORER_URL=http://scorer:8020` in `.env`. The first
  start downloads about 500 MB into the `scorer-models` volume.
- Measured (14 Nov 2026, the agent's sandbox): about 780 MB resident, 0.12–0.16 s per essay, 3.4 s to load.
- Essays over 512 tokens (roughly 380 words) are cut; the response says so (`truncated`).
- Tests use a tiny random model built offline: `uv run pytest -q`.
