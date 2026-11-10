# planv2.md — P2: chạy local và tích hợp Deep Research

## 1. Mục tiêu và hiện trạng

Chạy backend, database, embedding và worker trên máy cá nhân; tích hợp luồng người dùng nhập chủ đề → Deep Research tìm/đọc/lọc nguồn → index → tạo sơ đồ và câu hỏi đã kiểm chứng → học và lưu tiến độ. A đã hoàn thành; kiểm tra tự động trong B đã đạt; C còn thiếu tích hợp và nghiệm thu dịch vụ thật. Mục 6–8 là lịch sử; mục 9 là bằng chứng kiểm tra gần nhất.

**Quyết định đã chốt với người dùng (2026-11-07):**

- Ưu tiên hoàn thiện P2 và tích hợp Deep Research thật. C tiếp tục ngay; không chờ sách tải sẵn hay hoàn tất benchmark một chương mới triển khai C.
- Chỉ sửa các phần thuộc P2 theo `TEAM.md`; dùng code hiện có của các lane khác, không tự triển khai thay phần bàn giao còn thiếu.
- Máy cá nhân: RAM 32 GB, GTX 1060 VRAM 6 GB. Giữ phương án bge-m3 CPU cho mốc đầu; chưa cần cấu hình GPU. Đo thời gian và RAM khi index nguồn thật.
- Người dùng hiện có DeepSeek API. Test tự động dùng fake không cần key; nghiệm thu Deep Research thật cần cấu hình search và LLM qua gateway P3, cùng model generator/verifier khác họ theo contract.
- `deep` tìm và đọc nguồn trực tiếp theo chủ đề, kiểm tra nguồn/giấy phép và giữ provenance trước khi index. Không yêu cầu người dùng nhập sách thủ công hoặc P3 bàn giao sách tải sẵn.
- `quick` dùng thư viện đã index hoặc tài liệu upload, không tìm web. Nguồn sách chuẩn bị trước phục vụ thư viện/benchmark; golden topic phục vụ test, không thay thế nghiệm thu Deep Research thật.
- Chưa ấn định deadline; tiếp tục theo thứ tự công việc ở mục 4, ưu tiên phần P2 và ghi rõ phụ thuộc các lane.

**Đã có:** FastAPI, Docker Postgres + pgvector, contracts/engine/retrieval P1, routes P3, web P5, database services P2, queue/worker và trạng thái topic/SSE. Migration hiện có: `0001–0004`, `0006–0008`.

**Còn thiếu để nghiệm thu Deep Research thật:** migration `0005`, adapter nối các ports tìm nguồn/index/lưu DB/sinh và kiểm chứng nội dung, backend tutor P4, cấu hình search/gateway/embedding thực tế và lượt chạy xuyên suốt. Gateway P3 đã có code nhưng chưa kiểm chứng bằng gọi model thật trong đợt P2 này. Thiếu dữ liệu sách raw chỉ ảnh hưởng benchmark/thư viện chuẩn bị trước.

Kế hoạch này bổ sung hướng chạy local; giữ `TEAM.md` làm nguồn chính thức cho quyền sở hữu và contracts. Không áp mốc giờ thi cho tiến độ local. `[x]` là phần đã thực hiện theo bằng chứng ghi nhận; `[ ]` là phần chưa nghiệm thu. Test fixture không chứng minh luồng dịch vụ thật đã hoạt động.

## 2. Giai đoạn A — Chạy được backend hiện có

**P2 thực hiện theo thứ tự:**

- [x] Kiểm tra Docker Desktop chạy Linux containers, Python 3.12, Git và `uv`.
- [x] Hướng dẫn người dùng tự sao chép `.env.example` thành `.env`; không đọc hoặc ghi đè file secrets đã tồn tại.
- [x] Dùng database local: `postgresql://postgres:postgres@localhost:54322/nodetrail`.
- [x] Từ repo root, chạy `docker compose up -d db`; chờ database healthy.
- [x] Tại `apps/api`, cài dependencies, chạy migration và khởi động API:

  ```powershell
  uv sync --locked
  uv run python -m app.migrate
  uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
  ```

- [x] Xác nhận `http://localhost:8000/health` trả `status=ok`, `db=ok`; mở được `http://localhost:8000/docs`.
- [x] Viết hướng dẫn PowerShell cho khởi động, dừng, xem log và xử lý cổng bị chiếm. `docker compose down` giữ dữ liệu; thao tác xóa volume phải được ghi riêng là reset dữ liệu.

**Hoàn thành khi:** database và API khởi động được sau khi restart, migration chạy lại không tạo thay đổi, dữ liệu vẫn còn sau khi dừng container.

## 3. Giai đoạn B — Test và dữ liệu local

### B1. Kiểm tra tự động — đã đạt

- [x] Giữ fixture tạo **database tạm mỗi lần chạy test** hiện có; chưa chuyển sang schema tạm vì Postgres local cho phép tạo database.
- [x] Chạy các kiểm tra sau tại `apps/api`:

  ```powershell
  uv run pytest -q
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy .
  ```

- [x] Ghi nhận riêng kết quả `mypy`; CI đã đồng bộ thành warn-only theo `TEAM.md`.
- [x] Xác nhận test không tác động dữ liệu dev; lượt kiểm tra gần nhất giữ nguyên 0 dev chunks.

### B2. Benchmark ingest riêng — chưa nghiệm thu, không chặn C

Mục tiêu là đo hiệu năng CPU và kiểm chứng pipeline lưu vector/provenance. Một chương Think Python là dữ liệu benchmark đề xuất ban đầu, không phải nguồn bắt buộc cho sản phẩm. Có thể dùng nguồn thật hợp lệ từ Deep Research để kiểm chứng index; nếu dùng nguồn khác thì ghi rõ định dạng và pipeline tương ứng.

- [ ] Có nguồn thật được kiểm tra giấy phép và provenance: dùng kết quả Deep Research hoặc file do P3 chuẩn bị cho benchmark/thư viện.
- [ ] Khởi đầu bằng `BgeM3Embedder` CPU đang có: cài extra `embed`, tải model ở lần chạy đầu và đo trên một nguồn nhỏ trước khi mở rộng. Không bắt buộc GPU hoặc TEI cho mốc chạy local đầu tiên.
- [ ] Ghi thời gian index, RAM cao nhất, model/device, số chunks và kích thước DB.
- [ ] Nếu benchmark bằng notebook Think Python 3e tại `data/raw/thinkpython`, chạy tại `apps/api`:

  ```powershell
  uv sync --locked --extra embed
  uv run python -m app.rag.ingest ../../data/raw/thinkpython --embedder local
  ```

- [ ] Kiểm tra ingest lại không nhân đôi chunks, vector đúng 1024 chiều và provenance được lưu.
- [ ] Nếu dùng export sách `source.json` + `document.json`, dùng CLI `app.rag.library` của P1; không đưa export này vào CLI notebook ở trên. Nguồn tìm trực tiếp đi qua port `index` của pipeline.

**Hoàn thành B1 khi:** test dùng fake embedder chạy không cần tải model hoặc gọi LLM, dữ liệu dev không bị test tác động. **Hoàn thành B2 khi:** có kết quả index nguồn thật, số đo và kiểm tra ingest lại/vector/provenance đạt.

Hiện B1 đã đạt, B2 chưa đạt. Không dùng fake embedder để thay thế nghiệm thu index thật; không chờ bàn giao sách tải sẵn để tiếp tục tích hợp Deep Research.

## 4. Giai đoạn C — Tích hợp Deep Research, công việc ưu tiên hiện tại

### Nền tảng đã có

- [x] Trước module/API mới, lập spec theo quy trình Spec Kit của repo; dùng contract do P1 cung cấp. Artifacts được viết thủ công; CLI chưa khởi tạo.
- [x] Cung cấp API stubs theo contract để P5 phát triển giao diện; đánh dấu rõ dữ liệu fixture. Routes P3 đã mount; tutor chưa có backend trả 503.
- [x] Viết database services cho attempts, mastery, decision traces và review cards; engine của P1 tiếp tục độc lập database.
- [x] Viết migration `0006` cho `topic_jobs`, `llm_calls`; không sửa migration thuộc lane khác.
- [x] Xây queue Postgres và worker chạy bằng process riêng; claim job bằng `FOR UPDATE SKIP LOCKED`, ghi tiến trình và trạng thái lỗi.
- [x] Cung cấp trạng thái topic và SSE theo contract; heartbeat mỗi 15–20 giây, hỗ trợ client kết nối lại và tải trạng thái hiện tại.
- [x] Thêm cấu hình local cần thiết: CORS cho `http://localhost:3000`, API key dùng chung và địa chỉ API `http://localhost:8000`. Các biến hiện có trong `.env.example` chưa đồng nghĩa đã được code hỗ trợ.
- [x] Thêm log có `request_id`, `topic_id`, `tier`; Langfuse là tùy chọn local, thiếu credentials không chặn khởi động.
- [x] Bổ sung adapter P2 index tài liệu P1: transaction, giữ ID khi retry, chống ghi trùng đồng thời và rollback khi embedding lỗi; kiểm tra bằng fake, chưa nghiệm thu embedding thật.
- [x] Worker truyền settings search/provider/model sang gateway P3 trước khi nạp factory; không in secrets và giữ ưu tiên biến môi trường shell.
- [x] Cài Spec Kit CLI, scaffold Claude/PowerShell, giữ constitution và kiểm tra dry run không đổi nhánh.

### Công việc tiếp theo, theo thứ tự

1. [ ] Chốt bàn giao P1/P3/P4: cấu hình search, gateway và model roles; chữ ký các adapter; ánh xạ item → concept và migration `0005`. P2 tiếp tục phần wiring/persistence đã có contract trong lúc chờ, không tự tạo nội dung hay cờ verified thay P4.
2. [ ] Hoàn thiện adapter/factory P2 trong `app/services/` để nối `TopicPipeline` hiện có: nhận nguồn do P3 tìm/lọc → index bằng P1 → lưu chunks và provenance → gọi P4 sinh/kiểm chứng → lưu graph/items. Truyền cấu hình embedding thật qua `make_embedder`; các bước lưu phải an toàn khi thực hiện lại theo contract.
3. [ ] Review/merge migration theo thứ tự `TEAM.md`; sau khi có `0005`, migrate DB local và xác nhận chạy lại an toàn, restart không mất dữ liệu. Không fabricate migration còn thiếu hoặc dùng schema test để tuyên bố dev DB đã sẵn sàng.
4. [ ] Cấu hình dịch vụ thật bằng biến môi trường; nối gateway P3 và generator/verifier khác họ. Xác minh từng dịch vụ trước lượt chạy tổng thể; không đọc/in secrets. Chỉ cấu hình Storage nếu nghiệm thu upload file.
5. [ ] Chạy worker process riêng với factory thật; kiểm tra `deep` từ queued → researching → indexing → graph → items → ready, hoặc failed có nguyên nhân phù hợp. Không dùng factory ví dụ trong handoff khi module chưa tồn tại.
6. [ ] Chạy web ở API mode: nhập chủ đề chưa chuẩn bị trước → xem nguồn/tiến trình → placement → trả lời MCQ → lưu mastery/trace/review → mở trích dẫn. Nối tutor khi P4 bàn giao backend đã kiểm chứng.
7. [ ] Đo thời gian/RAM index nguồn tìm được và kiểm tra B2; kiểm tra lỗi search/LLM/DB, SSE heartbeat/reconnect và cạnh tranh giữa hai worker. Ghi rõ giới hạn phục hồi job nếu worker dừng sau claim.
8. [ ] Hoàn tất phần thiết lập Spec Kit CLI còn thiếu, cập nhật runbook và bằng chứng nghiệm thu. Chỉ đánh dấu hoàn thành các mục đã chạy và quan sát được.

**Phụ thuộc tích hợp:**

| Thành viên | Trạng thái và phần cần cho tích hợp thật |
|---|---|
| P1 | Contracts, engine, retrieval và `0003–0004` đã có; dùng interfaces hiện có để nối embedding/index |
| P3 | Routes, research pipeline và gateway đã có code; cần xác minh search/đọc/lọc nguồn và gateway thật; không bắt buộc bàn giao sách tải sẵn cho `deep` |
| P4 | Cần `0005`, sinh/kiểm chứng graph/items, ánh xạ item → concept và tutor; golden topic chỉ phục vụ test |
| P5 | Web đã có và qua code checks; cần nghiệm thu API mode trên browser. Client hiện polling; SSE backend cần kiểm tra riêng, không coi polling là đã có SSE reconnect trên web |

LLM chỉ được gọi qua gateway của P3. DeepSeek là API người dùng hiện có, chưa xác nhận gateway hỗ trợ và chưa chọn model hoặc ngân sách. P3/P1 cần chốt cấu hình theo contracts; chỉ có DeepSeek chưa đủ đáp ứng yêu cầu generator/verifier khác họ model. Đây là phụ thuộc nghiệm thu dịch vụ thật; không chặn code/test P2 dùng fake.

## 5. Nghiệm thu và giới hạn

**Hạ tầng và kiểm tra tự động:**

- [x] Máy mới có thể làm theo hướng dẫn để chạy DB, migrate, API và test.
- [x] Đạt điều kiện hoàn thành A: khởi động lại được, migration chạy lại an toàn và dữ liệu còn sau khi dừng container.
- [x] Đạt B1: test cô lập dữ liệu dev và ghi nhận kết quả kiểm tra.
- [ ] Đạt B2: index nguồn thật, có số đo hiệu năng, không nhân đôi chunks, vector 1024 chiều và có provenance. Có thể dùng nguồn từ Deep Research; không bắt buộc sách tải sẵn.
- [x] Checklist ghi rõ phần đã chạy thật, phần dùng fixture và phần đang chờ bàn giao.

**Điều kiện hoàn thành P2 local và tích hợp Deep Research:**

- [ ] Migration local đầy đủ, chạy lại an toàn và dữ liệu tồn tại sau restart.
- [ ] Chủ đề chưa chuẩn bị trước chạy qua Deep Research thật: tìm/đọc/lọc ít nhất 3 nguồn từ 2 nhà xuất bản, lưu giấy phép/provenance và chunks thực.
- [ ] Worker thật xử lý topic đến ready/failed; graph/items chỉ ready sau khi đã kiểm chứng và lưu DB. Test claim cạnh tranh đã có; cần ghi nhận vận hành với hai worker.
- [ ] SSE thật có tiến trình, heartbeat và tải lại snapshot hiện tại sau ngắt kết nối; không yêu cầu replay lịch sử chưa được triển khai.
- [ ] Web API mode → nhập chủ đề mới → placement → trả lời MCQ → lưu mastery/trace/review → xem trích dẫn; tutor được nghiệm thu sau bàn giao backend P4.
- [ ] Lỗi search, nguồn không đủ, database hoặc LLM có thông báo và log truy tìm; không báo thành công giả hoặc tự đổi sang golden fixture.
- [ ] Ghi bằng chứng thời gian toàn luồng `deep` theo giới hạn contract 8 phút, thời gian/RAM index, kết quả kiểm tra và các giới hạn còn lại.

**Mặc định:** API/worker chạy trực tiếp bằng `uv`, chỉ database chạy Docker; embedding dùng CPU và cùng model bge-m3. Chưa yêu cầu Docker hóa toàn bộ ứng dụng.

**Hoãn khỏi đợt local:** cloud VM, AWS backup VM, Cloudflare Tunnel, GHCR/Watchtower và deploy Vercel. Deep Research và demo chủ đề bất kỳ thuộc đợt tích hợp hiện tại; không cần hoàn tất golden topic hay tải sẵn thư viện trước. Upload và thư viện chuẩn bị trước là các luồng bổ sung, nghiệm thu riêng khi được triển khai/cấu hình đầy đủ.

## 6. Acceptance record - 2026-11-07

> Historical A–B record; its chapter handoff and missing-code statements do not define the current integration priority. See sections 1–5 and 8.

**A complete; B partially complete, awaiting P3's chapter handoff.**

- PowerShell runbook and detailed evidence: [docker/LOCAL.md](docker/LOCAL.md).
- Installed uv 0.13.7 and uv-managed Python 3.12.16; Docker Linux; Git 2.56.0.
- Database healthy. Migrations 0001-0002 applied, repeated safely, and survived Compose down/up.
- API restarted successfully: /health status=ok, db=ok; /docs HTTP 200.
- pytest: 133 passed, one TestClient/httpx dependency deprecation warning.
- Ruff lint/format passed; mypy passed on 25 files. CI mypy is now warning-only.
- Existing per-session temporary database fixture retained; dev chunk count stayed zero after tests.
- Instructions provided for user-managed .env copying. No secrets file read or created; default local DB used.
- data/raw/thinkpython is absent: embed extra/model download, real ingest, elapsed time, peak RAM and real vector/provenance acceptance remain pending. Fake embeddings do not satisfy this acceptance.
- Migration 0003 has not been handed off; no P1 vector changes available to review/merge.
- Phase C started on user instruction; see the record below.

## 7. Phase C implementation record - 2026-11-07

> Historical foundation record. Missing components described here may now exist; section 8 records the latest verification.

**P2 foundation implemented and tested; C remains partially complete pending lane handoffs.**
This supersedes the earlier decision to defer C. The missing book does not block platform work.

- Spec/plan/tasks written before code in `specs/p2-local/`; constitution in `.specify/memory/constitution.md`. Spec Kit CLI/commands are absent; manual artifacts do not imply CLI initialization is complete.
- P2 endpoints implemented from TEAM.md: POST /learners; GET /topics/cached; GET /topics/{id}; GET /topics/{id}/events. P1 schemas.py is still absent. Full P3 business stubs remain pending that schema handoff; no P3-owned files edited.
- Attempts/mastery/review persistence implemented with caller-owned transactions. Atomic rollback tested. Decision traces still await P1 migration 0004 and schema; the services checkbox remains incomplete.
- Migration 0006_platform.sql adds topic_jobs and llm_calls. Temporary test databases apply it successfully. Dev/shared DB application is deferred until 0003-0005 arrive and are reviewed in TEAM.md order.
- Queue claims use FOR UPDATE SKIP LOCKED; independent worker process supports explicit fixtures, persists missing-P3 failures, and does not mark real jobs ready. Concurrent claim test passed.
- Topic GET and SSE share a durable snapshot. SSE polls changes, emits heartbeat every 15 seconds and sends current state on reconnect. Heartbeat/progress/reconnect tested. No historical event replay is promised.
- Local CORS and optional X-API-Key are supported; request IDs and structured JSON logs added using standard logging. Langfuse is not initialized, so missing credentials cannot block startup; gateway telemetry still awaits P3.
- Verification: 137 tests passed; ruff lint and format passed; mypy passed on 32 files. Existing dependency warning: TestClient/httpx deprecation. Web checks skipped because apps/web is absent.
- Operational instructions and limits: docker/LOCAL.md. Crash-after-claim recovery is manual until P3 provides an idempotent pipeline contract. Real processing, actual LLM failures and full web integration have not been exercised.
- B real ingest remains pending P3's licensed chapter. No real model/LLM requests, new dependencies, commits or pushes.

## 8. Integration verification update - 2026-11-07

**A complete; B real ingest and C live content acceptance remain pending.**
This record supersedes the missing-code statements in sections 6–7.

**Clarification:** receiving a pre-downloaded book from P3 is not a prerequisite
for running Deep Research. The `deep` pipeline searches/reads sources live, then
indexes them before graph/item generation. The `quick` pipeline uses the curated
library or an upload and does not invoke web search. The chapter handoff above
belongs to the original B ingest benchmark; it must not block P2's Deep Research
integration work. That benchmark remains unverified until a real source is ingested.

- Existing integration work in this checkout connects P3 learning/topic routers to
  P2 database adapters, private upload storage and the independent pipeline worker.
  Spec and remaining tasks: `specs/p2-integration/`.
- Learning persistence includes attempts, mastery, decision traces and FSRS review
  cards. Isolated tests cover rollback on trace failure, concurrent updates,
  placement completion without resetting later mastery and rejection of unverified items.
- Added P2 settings `EMBEDDING_BACKEND` (`local`/`tei`), `TEI_URL` and secret-masked
  `TEI_API_KEY`; aligned `.env.example` with local CPU use. Verified settings can
  construct P1's TEI client without network/model access. Adapters must pass these
  settings to `make_embedder`; no unused retriever/model is loaded at API startup.
  P1 indexing CLIs still use `--embedder`, `--tei-url` and `TEI_API_KEY` from the shell.
- Fixed the P2 integration test's outdated hint level (0 → 1) to match the current
  P1/P3 contract (1–4). Regenerated `specs/p2-integration/openapi.json`; optional
  `last_answer` is a zero-based integer, not a string.
- Verification: **1172 API tests passed**, Ruff lint/format passed, mypy passed on
  113 source files. Existing Starlette/TestClient httpx deprecation warning remains.
  **38 web tests passed**, ESLint, TypeScript and production Next.js build passed.
  Dev chunk count was zero before and after this verification run.
- Reviewed delivered migrations 0003–0004 and upload/input migrations 0007–0008;
  temporary databases apply all available migrations successfully. Shared/dev DB
  migration remains deferred until P4's reserved 0005 arrives; no gap was fabricated.
- Acquisition/index receipts exist under `data/sources/`, but `data/raw/` is absent
  on this machine. Those receipts do not establish local ingest or vector acceptance.
  A prebuilt-library benchmark needs the actual licensed files, not only receipts;
  Deep Research obtains its sources live and does not wait for that handoff.
- Remaining P4 handoff: migration 0005, generation/gates, reliable item-to-concept
  mapping and a real worker pipeline factory. Tutor backend is also unavailable.
  Worker fixture/fake-port tests do not satisfy live topic generation acceptance.
- No real embedding/LLM/Storage requests, shared DB migrations, browser acceptance,
  deployment, new dependencies, commits or pushes in this continuation.

## 9. P2 continuation — 2026-11-07

**P2 indexing/runtime/Spec Kit improved; the complete plan is not yet accepted.**

- Added `app/services/indexing.py`: P1 SourceMeta/ParsedDocument → P1 chunker and
  embedder → transactional source/chunk persistence → persistent PreparedChunk IDs.
  Identical retries preserve IDs and skip embedding; concurrent retry embeds once.
  Empty text, incompatible dimensions and changed snapshots fail explicitly; an
  embedding failure rolls back source/subject/chunks. A changed snapshot requires
  a new source identity so existing citations cannot silently disappear.
- The indexing helper lazily calls `make_embedder` with P2 embedding settings when
  no embedder is supplied. This path is tested with an injected fake factory;
  downloading/running bge-m3 CPU and measuring RAM/time remain B2 work.
- Worker startup forwards the supported P3 search/provider/model settings before
  loading the pipeline factory, retaining shell precedence and masking credentials.
  Root `.env.example` now lists Brave selection and all ten model-role variables.
  No developer tool read `.env`; no real provider call was made.
- Spec Kit CLI `1.3.3.dev0`, revision
  `c43849408ac0de2ca6a52f14eaae71449776057b`, installed as an isolated uv tool.
  CLI initialization ran in a temporary folder; its 27 non-memory scaffold files
  were copied after collision checks, preserving the project's constitution.
  `specify check` and the PowerShell feature dry run passed. This version installs
  `/speckit-specify`, `/speckit-plan`, `/speckit-tasks` skills and does not switch
  branches during feature creation. Existing `ptest` and manual specs were retained.
- Verification: **1179 API tests passed**, Ruff lint/format passed, mypy passed
  on 115 source files; **38 web tests**, ESLint and TypeScript passed through
  `npm.cmd` package scripts (pnpm is absent from PATH). `git diff --check` passed.
  The existing Starlette/httpx deprecation warning remains. Dev chunks were zero
  immediately before and after this continuation's checks.
- No production pipeline factory was fabricated. P4's `app/content/`,
  `app/guardrails/`, `app/tutor/` and reserved migration `0005` are absent.
  Source naming/coverage and reliable item-to-concept mapping still need the
  P1/P3/P4 handoff before graph/item persistence and the full factory can be wired.
  The document-index helper alone does not complete C2.
- Remaining acceptance: P4 handoff and factory; ordered dev migrations; actual
  search/model configuration with different generator/verifier families; real
  bge-m3 indexing and benchmark; worker/SSE/browser learner flow and failure
  acceptance. DeepSeek alone is unsupported by the current P3 gateway and cannot
  establish its Gemini/Claude verification contract. No live readiness is claimed.

P1 MAP update proposal: add `app/services/indexing.py`, mark P2 router/worker
wiring and P5 web present, and replace the old missing-web/factory descriptions
with the current P4 dependencies. MAP.md remains P1-owned under TEAM.md.
