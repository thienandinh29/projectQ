# Demo upload consent

Uploads are disabled by default. Set `DEMO_UPLOADS_ENABLED=true` in the API and
worker environment only for the competition demo; apply migration `0011` first.
Keep `API_KEY` configured independently.

The upload dialog shows the exact Vietnamese notice from `SPEC.md`. The checkbox
starts unchecked and the file picker stays disabled until acceptance. The client
sends `X-Demo-Upload-Consent: demo-v1` only after acceptance; the same-origin proxy
forwards that exact value. Unchecking clears the selected upload from the form.

`POST /uploads` rejects disabled demo mode or missing/unknown consent before
reading the body, parsing a file, or fetching a link. Accepted uploads store
`uploads.demo_consent_at`. Old uploads have no consent timestamp. The worker
requires both demo mode and that persisted timestamp before indexing an upload or
sending its content to a model. `POST /topics` also rejects upload IDs outside demo
mode. There is no production permission implied by a previous demo consent.

Validation: API upload policy and persisted-consent/worker tests cover file and
link rejection, accepted uploads, missing consent, and disabled demo mode. Web
client/proxy tests cover refusal before consent and exact consent forwarding.
This does not establish provider privacy terms or authorize real-learner uploads.


After the demo, stop the worker, then from `apps/api` run:

```powershell
uv run python -m app.uploads.purge --all-demo
# Or delete a single upload:
uv run python -m app.uploads.purge --upload-id <UUID>
```

Purge rejects active jobs, deletes queued/finished upload-owned topics and their
chunks, attempts, mastery, reviews, traces, caches, audits and retry receipts, then
removes the private object and upload row. Object-storage failure rolls back the
DB transaction; retrying an absent upload is safe. Curated library subjects remain.

`POST /attempts` accepts optional `client_attempt_id` (UUID, additive contract).
Clients must preserve the same ID and body across network retries, and allocate a
new ID for a new submitted answer. Requests omitting it retain legacy per-request
behavior. A conflicting body under an existing ID returns 409; a matching retry
returns the entire original result even if the question was later changed/withdrawn.
