# Bàn giao sửa luồng research và phát hành bài học

Mục tiêu rộng hoặc nguồn không phù hợp từng tạo graph trước khi có đủ câu hỏi
đạt kiểm chứng. Một số lỗi trích dẫn và thay đổi dữ liệu dùng chung còn làm mất
hiệu lực câu hỏi đã kiểm chứng. Commit này sửa backend và test, không bao gồm UI
thử nghiệm hay log/credential local.

## Luồng và điều kiện phát hành

Mục tiêu → lập truy vấn → tìm/đọc nguồn → kiểm tra giấy phép và nội dung giảng dạy
→ lưu/embedding → lấy context → graph nháp → sinh/kiểm chứng câu hỏi cho từng
khái niệm → lưu và kiểm tra lại → phát hành → người học xem/xác nhận → học.

- Graph nháp được lưu làm checkpoint; `graph_ready=false` cho tới khi các câu hỏi
  đủ điều kiện và đã được lưu. Lỗi kiểm chứng không phát hành graph nháp.
- API xem graph, review, confirm và bắt đầu học chặn topic chưa có trạng thái
  `ready` cùng cả hai cờ `graph_ready`/`items_ready`. Không cần migration mới.
- Worker `--pipeline` giới hạn bài đầu ở 3 khái niệm và 6 đoạn context. Graph giữ
  quan hệ tiên quyết hợp lệ; checkpoint cũng phải tuân thủ giới hạn/context mới.
- Số câu hỏi đạt kiểm chứng tối thiểu là 6 và phải phủ mọi khái niệm. Lỗi coverage
  nêu rõ tên khái niệm, không quy mọi thất bại thành thiếu tài liệu.

## Sửa các điểm tích hợp

- Quick chọn thư viện theo mục tiêu thay vì ghim mặc định Python.
- Deep hỗ trợ Brave và Tavily; Tavily dùng basic search, không tự nâng độ sâu.
  Truy vấn được chuẩn hóa từ mục tiêu, gồm tiếng Việt không dấu. Các biến thể dùng
  chung ngân sách tối đa 15 search/12 lượt đọc và deadline Deep hiện hữu.
- Chỉ xếp hạng URL được nhà cung cấp trả về. Đọc trang thật, kiểm tra giấy phép và
  yêu cầu chọn đoạn giảng dạy thực sự liên quan trước khi chọn nguồn.
- Nguồn web mới và upload được lưu/embedding trong đúng topic. Nội dung đổi làm
  vector cũ mất hiệu lực; retry giữ các batch embedding đã hoàn tất.
- Chunk prompt có ánh xạ source ID rõ ràng. Câu hỏi giữ provenance và dùng model
  family độc lập để kiểm chứng; không truyền đáp án chuẩn vào request verifier.
- Mô tả misconception dùng chung được cố định trước kiểm chứng; lưu câu mới không
  ghi đè mô tả khiến hash của câu cũ thay đổi.
- Trích dẫn sai định dạng được sửa tối đa một lần trong deadline kiểm chứng cũ,
  chỉ khi verdict độc lập đã đạt các điều kiện khác. Vẫn cần quote khớp nguồn thật;
  không retry câu trả lời sai, lỗi provider hoặc verdict không an toàn.
- Công cụ import checkpoint chỉ ghi câu còn hợp lệ theo hash, mặc định dry-run và
  CLI chỉ cho phép PostgreSQL local.

## Cấu hình và kiểm tra

Điền credential vào `.env` local từ `.env.example`; không đưa vào Git. Với Tavily:
`SEARCH_PROVIDER=tavily`, `SEARCH_API_KEY=<key local>`. Cấu hình database, TEI và
model generation/verification có model family độc lập trước khi chạy worker.

Từ `apps/api`, dùng môi trường Python đã cài dependency của dự án:

```powershell
python -m app.research.search          # chỉ kiểm tra cấu hình, không gọi mạng
python -m app.research.search --live   # một truy vấn search thật
python -m app.jobs.worker --pipeline
```

Các lệnh CI: `ruff check .`, `ruff format --check .`, `mypy .`, `pytest -q`.
Kiểm tra local: **1.489 test pass**, Ruff/format và mypy toàn bộ API/test pass.
Test PostgreSQL dùng database tạm riêng; có kiểm tra graph nháp/failed bị chặn
ở cả review, confirm, graph và placement, cùng luồng published → học thành công.

Các lượt smoke local đã chạy research thật cho xác suất, sinh học và ngữ pháp
tiếng Anh, gồm DB/RAG, xác nhận graph, placement, luyện tập và hint. Đây là kiểm
tra tích hợp bằng người học giả lập; chưa phải kiểm chứng hiệu quả giáo dục hay
độ ổn định cho mọi mục tiêu. Không tuyên bố production GO hoặc tiết kiệm token
định lượng từ các kết quả này. Log và receipt local không nằm trong commit.

## Sửa luồng tài liệu toán và truy xuất

Lượt kiểm tra “học đạo hàm” phát hiện lỗi ở backend, trước khi frontend có thể
hiển thị bài học: trang tải PDF bị coi như nội dung, trích dẫn công thức bị model
chép lại sai định dạng, rồi truy vấn RAG tiếng Việt chọn macro TeX và khung giao diện
trong tài liệu tiếng Anh. Có nguồn tìm được nhưng không có ngữ cảnh tốt để sinh bài.

- Bộ xếp hạng xét tối đa 24 ứng viên từ hai truy vấn thay vì cắt mỗi nhóm còn sáu;
  vẫn chỉ đọc tối đa 12 nguồn và chỉ chấp nhận URL đã được search trả về.
- MIT dùng cụm chủ đề ngắn để tìm trang chương. Reader chỉ theo liên kết PDF thực
  sự xuất hiện trên trang resource, đúng khóa học và tệp. Trang và PDF đều tính vào
  ngân sách đọc; giữ kiểm tra SSRF, giấy phép, hạn chế AI và hạn chế trong chính tệp.
- Nếu search trả về mục lục MIT, reader lấy tối đa 12 liên kết chương thực trong
  cùng khóa học rồi xếp hạng theo mục tiêu; không coi mục lục là bài học và không
  truyền giấy phép của mục lục thay cho giấy phép trang chương/tệp.
- Giấy phép của trang resource được giữ cùng URL provenance; chunk PDF giữ số trang
  và văn bản của từng trang, không lặp toàn bộ tệp cho mỗi trang.
- Kiểm tra liên quan chọn ID đoạn văn do server cấp, tránh chép lại công thức.
  Việc kiểm chứng đáp án vẫn dùng model family độc lập và kiểm tra bằng chứng cũ.
- Reader lấy phần bài học LibreTexts cho indexing; văn bản HTML đầy đủ vẫn được
  kiểm tra riêng về giấy phép. Truy vấn research chuẩn hóa được truyền tiếp vào RAG,
  còn mục tiêu gốc của người học vẫn được dùng để kiểm tra phạm vi bản đồ.
- RAG của job chỉ tìm trong chunk hiện tại. Tài liệu cũ còn lưu sau retry không được
  trộn vào ngữ cảnh mới; SQL loại cả vector null. Lỗi bất ngờ ghi stage, loại exception
  và vị trí hàm/dòng, không ghi nội dung exception hay khóa. Lỗi bước câu hỏi được
  báo riêng thay vì gộp thành “không thể xây lộ trình”.

Test hồi quy bao gồm PDF thực được liên kết, ngân sách đọc, giấy phép ND và quyền
trong tệp, provenance từng trang, công thức toán, loại bỏ UI/macro, ứng viên ở cuối
hai trang search và truy vấn chuẩn hóa đi tới retriever. Test tích hợp vẫn kiểm tra
Deep → SQL → xác nhận bản đồ → placement → practice bằng người học giả lập.

Sau các sửa đổi này: toàn bộ **1.508 test pass**, Ruff check/format và mypy pass.
Một lượt sinh câu hỏi thật đã tạo sáu câu được kiểm chứng trên checkpoint đạo hàm;
đây chưa đủ để kết luận cả luồng research ổn định. Telemetry của lần lỗi đã ghi nhận
DeepSeek trả 4.096 output token, `deepseek_incomplete_response`, 4.484 input token.
Task `items` trước đó dùng trần mặc định 4.096 dành cho câu trả lời đơn nên batch
câu hỏi toán bị cắt. Trần riêng `items` được sửa thành 16.384 như task graph; đây là
giới hạn tối đa, không phải lượng token buộc dùng. Retry/deadline/verifier không đổi.

Sau khi tăng trần, cùng bước sinh trả đủ 7.045 output token trong khoảng 26 giây.
Một blocker khác là verifier chép lại công thức LaTeX không đúng nguyên văn, gây
`invalid_or_missing_evidence` và nhiều cuộc gọi kiểm tra dẫn tới 429. Request blind v3
cung cấp các đoạn nguồn có ID; verifier chọn ID, backend gắn lại nguyên văn rồi vẫn
kiểm tra nguồn, đáp án, tính duy nhất và model family như trước. Audit v2 hợp lệ vẫn
được đọc; manifest diagnostic v2 được giữ nguyên để không thay đổi lịch sử kiểm tra.

Retry còn tái hiện `UniqueViolation`: tiêu đề search đổi nhưng URL vẫn như cũ.
Repository giữ định danh book hiện hữu cho cùng source ID, tránh insert trùng khóa;
test PostgreSQL kiểm tra chunk ID/index/provenance được giữ khi tiêu đề thay đổi.

Hint gặp cùng lỗi chép công thức và được sửa bằng cùng cơ chế bind passage ID.
Schema câu hỏi và hint có trường `passage_id` riêng, tránh model hiểu nhầm ID thành
văn bản trích dẫn. Audit vẫn lưu quote nguyên văn; ID không tồn tại bị chặn, model
family độc lập, kiểm tra đáp án và toàn bộ tiêu chí không lộ đáp án của hint giữ nguyên.
Runner paired evaluation cũng dùng cùng binder, gồm hỗ trợ đọc phản hồi quote v2.
Diagnostic cũ từ chối request v3 trước khi gọi mạng vì fingerprint không còn khớp
manifest v2; không gắn nhãn request mới bằng fingerprint lịch sử.

Lượt local `fe153986-f992-44b3-afdd-0ff8d7eff0b2`, mục tiêu “học đạo hàm”, đã đạt
`ready` qua worker bình thường sau các lần sửa/retry trong quá trình phát triển.
Bản đồ hiện có ba khái niệm, **11 câu verified thuộc đúng ba khái niệm** (4/4/3).
Đã chạy qua API proxy của web: learner mới → chặn placement trước xác nhận (409) →
review/confirm → placement → practice → hint có citation → đáp án sai/đúng → database.
DB có năm attempts, ba mastery, 14 decision traces, một review card; session ở pha
practice. Gửi lại cùng client_attempt_id không tạo attempt trùng.

Đây là smoke tích hợp có người học giả lập, không phải kiểm tra bằng thao tác UI hay
đánh giá sư phạm. Nguồn/search và quota provider vẫn là phụ thuộc bên ngoài; các lần
retry phát triển không chứng minh tỷ lệ thành công ngay lần đầu cho mọi chủ đề.

Kiểm tra toàn bộ sau thay đổi question/hint: **1.516 test pass**, Ruff check/format
và mypy pass; regression từ chối diagnostic không khớp cũng pass riêng.

## Tìm web mở rộng và báo lỗi có nguyên nhân

Deep production không còn giới hạn URL vào danh sách nhà xuất bản ban đầu. Research
tìm web rộng, tìm trong nhóm nguồn ưu tiên rồi dùng truy vấn web rộng khác nếu vẫn
thiếu nguồn hợp lệ. Các bước dùng chung trần 15 search/12 lần đọc và deadline cũ;
thường có tối đa sáu truy vấn trong ba nhóm. Nhà xuất bản ngoài danh sách được nhóm
theo miền, bảo thủ gộp các subdomain cùng miền thành một chủ nguồn. Vẫn cần ba tài
liệu từ hai chủ nguồn; không bỏ kiểm tra giấy phép, hạn chế AI, SSRF, DNS public,
TLS, redirect, dung lượng, nội dung giảng dạy hoặc verifier độc lập.

Reader nhận PDF bài giảng MIT có tên tệp chứa hash từ link `download-file` thực,
không đoán tên tệp. Mục lục sách có link chương cùng sách/cùng host được xếp hạng
và mở trong ngân sách đọc. Từng chương tự kiểm tra giấy phép; giấy phép mục lục
không tự cấp quyền cho chương không có giấy phép. Không theo các link ngoài sách.

Planner từng đổi nhầm mục tiêu DSA thành tiếng Anh. Prompt đã bỏ ví dụ quá thiên
về tiếng Anh; một request riêng kiểm tra bản dịch/truy vấn có giữ đúng mục tiêu
trước khi gọi search. Kế hoạch lệch chủ đề bị chặn với `research_goal_mismatch`.

`GET /topics/{id}` và SSE có thêm `failure` tùy chọn: `stage`, `code`, `message_vi`,
`action_vi`, `rejected_sources`. Báo cáo lấy từ trail bền vững, không cần migration.
Mã lỗi phân biệt thiếu giấy phép, ND, hạn chế AI, HTTP, không có kết quả, không có
ứng viên phù hợp và provider search không khả dụng. Lưu lỗi trail thất bại không
được ngăn việc ghi trạng thái terminal. Retry chỉ lấy lý do của lượt mới nhất;
job cũ được đánh dấu `legacy_failure` và vẫn có lý do loại nguồn nếu có trong trail.

Gate readiness chạy trước khi tải subject/graph. Job failed trước indexing không
còn thành 404/503 chung chung khi review, graph, confirm, placement hay next-item:
trả 409 kèm mã lỗi, bước lỗi và hướng xử lý. Kiểm tra thật qua proxy web trên cả job
cũ và job mới: cả mười request đều 409, không có attempt được ghi vào DB.

Demo P5 local đã hiển thị bước/mã lỗi, hướng xử lý, từng URL bị loại và tự mở nhật
ký khi failed. Không gộp các file UI demo còn đang chỉnh từ trước vào commit backend.
OpenAPI và phần kiểu TypeScript liên quan failure được cập nhật theo hợp đồng bổ sung.

Kiểm tra: **1.532 test API pass**, Ruff/mypy pass; **77 test web pass**, typecheck,
lint và production build webpack pass. Chưa kiểm tra giao diện bằng thao tác browser.
Lượt DSA `443b5223-78af-4404-a3b9-cc5f3a5a8d78` đã chọn được hai chương Pressbooks
ngoài danh sách cũ, nhưng vẫn **NO GO: 2/3 tài liệu, 1/2 chủ nguồn** sau sáu search và
12 lần đọc. Báo cáo lưu rõ thiếu giấy phép, ND, hạn chế AI và HTTP 403; không sinh
bản đồ/câu hỏi từ lượt failed. Đây chưa phải xác nhận DSA hoặc mọi chủ đề đều GO.

## Backend-only DSA regression, 2026-11-08

Exact input: `Cau truc du lieu va giai thuatj`, Deep/Pro, normal worker and live
Tavily/DeepSeek/Gemini, Postgres and local TEI. Fresh regression jobs were enqueued
through the existing queue to bypass the ready-topic cache; no fixture or manual
ready flag was used. API testing uses `http://127.0.0.1:8018`; frontend was untouched.

Root causes fixed:

- The author page for Open Data Structures listed a different ND-licensed book
  in a labelled related-resource list. That unrelated licence was incorrectly
  applied to the author's own CC BY 2.5 book. The reader now scopes permission
  evidence, retains HTTP Creative Commons metadata without fetching HTTP, and
  still rejects the document's own ND/AI restrictions and malformed scope markup.
- Research rejected whole PDFs above the upload page limit. Research now extracts
  only physical pages 1-40, records the total and sampled pages in the trail, and
  follows only observed supported publisher downloads. Ordinary uploads retain
  their 200-page limit; missing/ND permissions, encrypted/empty PDFs and size
  limits remain enforced. No claim is made about unread pages or a whole course.
- A direct PDF rejected before its official resource page stayed deduplicated
  even after that page linked the exact PDF and supplied permission. It is now
  rechecked from the downloaded document, without another HTTP read. Own-file
  restrictions still win. Recovered permission failures are removed from public
  rejection reports, while subsequent relevance failures remain visible.
- More documents from one selected publisher are deferred while seeking a second
  publisher. HTML lessons precede whole-book PDFs so unrelated downloads do not
  consume the read budget first. Limits remain 15 searches, 12 reads, 480 seconds,
  three documents and two source owners.

Historical development runs are retained: `99139f38-2229-41c9-8dc5-a2e08c9de31a`
failed source discovery; `d1bf2c89-0094-460f-b8dc-d0fabfe22963` reached ready and
passed the HTTP learning flow using MIT plus two Pressbooks chapters. A fresh
repeat `96692a77-9bae-426e-9dff-0fad2bd2da01` exposed the PDF deduplication bug;
`f7ceccee-9a04-4ebd-a931-bb391f24be37` still exhausted its read budget at two
sources/two owners before the HTML-first ordering correction.

Final backend regression: **1,551 tests passed**, Ruff check/format and mypy pass.
One existing Starlette/httpx deprecation warning remains. Local JSON/XML receipts
are under `outputs/` and are not committed. Credentials remain in ignored local
configuration. Live outcomes below distinguish a working case from a general
production/educational approval.

The subsequent fresh job `a31a5ae6-a16c-42cc-b73f-e25e0cd020bb` reached ready.
DB audit: Open Data Structures (53 chunks), Pressbooks Algorithms/Big-O (16),
and Pressbooks Recursion (29); all **98/98 vectors present**. Three graph concepts
have **2/2/2 currently servable verified questions**, generated by `deepseek-flash`
and independently verified by `gemini-3.5-flash-lite`. HTTP learner
`7f9661d1-e600-4c37-94aa-449d91ca6641` passed confirmation gating (409 before
confirmation), placement, practice, cited hint, wrong/correct submissions and
idempotent replay. DB: 5 attempts, 3 mastery rows, 14 decision traces, 1 review
card; final phase `practice`. An authenticated learner reviewing a failed job
received 409 with stage/code/action, rather than a missing-graph error.

Another independent job `5be6bfec-f22c-4d9a-930f-f66789672c93` exposed unstable
source relevance: the same author PDF was rejected as non-instructional. A live
diagnostic confirmed that the supplied head/tail excerpts were mostly contents
and preface. Relevance now samples head/middle/tail for long documents, with the
same **24,000-character total budget** and exact server-owned excerpt IDs. The
regression places genuine teaching only in the middle and asserts the context
budget and verbatim evidence. This improves evidence selection; it does not
bypass source relevance or demonstrate a statistical accuracy rate.

After the sampling change, fresh job `9d2aca30-b4bd-485e-96cf-5d023365ee6e`
selected the author PDF plus the two Pressbooks chapters in about 42 seconds,
with all 98 source vectors persisted. Final regression after this change:
**1,552 backend tests passed**, Ruff check/format and mypy passed.

That final job reached `ready` and passed the complete backend HTTP learner flow.
Its introductory graph has two concepts (interface and data-structure
implementation), with **3/3 independently verified questions**. All six questions
use DeepSeek generation and Gemini verification with distinct recorded families.
Learner `1b438343-2161-4d41-9cfa-5121473076b2` passed confirmation gating,
placement, practice, a cited hint, wrong/correct answers and duplicate replay.
DB: 4 attempts, 2 mastery rows, 12 decision traces, 1 review card; phase `practice`.

Decision: **GO for this backend introductory DSA demo case**. Historical failed
fresh runs remain documented; this is not a measured first-attempt success rate,
a full DSA curriculum, educational validation, or production approval. Source
availability, search/model variability, quotas and CPU embedding latency remain
external/runtime limits. Frontend/browser behavior was not tested in this run.
