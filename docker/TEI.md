# Local bge-m3 host (P2)

Run from the repository root with Docker Desktop running (Linux containers):

```powershell
docker compose up -d tei
docker compose logs -f tei
```

The first start downloads `BAAI/bge-m3` into the persistent `tei-data` volume.
The CPU image is intentional: TEI GPU images do not support P2's GTX 1060.
The container has an 8 GiB memory limit and restarts with Docker unless stopped.
The CPU batch token budget and effective input limit are 1024 tokens to keep
warmup and inference within this limit. Use `truncate=true` for long text;
content beyond 1024 tokens is truncated, so split long documents into chunks.
Keep Docker Desktop running and the computer awake while serving requests.

Set these in the root `.env` for API adapters, then restart API/worker processes:

```dotenv
EMBEDDING_BACKEND=tei
TEI_URL=http://localhost:8080
TEI_API_KEY=
```

The endpoint binds to this machine's loopback interface. It is not public.
Containers on the same Compose network should use `http://tei:80` instead.

Check health and generate normalized 1024-dimensional dense embeddings:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/info
$body = @{ inputs = @('Xin chao'); normalize = $true; truncate = $true } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/embed -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Ingestion CLIs use explicit flags, independently of `EMBEDDING_BACKEND`:

```powershell
cd apps/api
uv run python -m app.rag.library <library> --embedder tei --tei-url http://localhost:8080 --build-index
```

Time a chapter before bulk indexing the library on CPU. No indexing runs as part
of starting the service. Stop with `docker compose stop tei`; do not remove the
volume if you want to retain the downloaded model.

Verified on P2's machine: `/health` returned HTTP 200; the project's sync and
async TEI clients returned normalized 1024-dimensional vectors. A short
Vietnamese async query took about 0.39 s (one sample, not a load benchmark).
The default 32-text client batch and long-input truncation were also checked.
Client/config tests: 23 passed.

Image hardware reference: [Hugging Face TEI supported hardware](https://huggingface.co/docs/text-embeddings-inference/supported_models).
