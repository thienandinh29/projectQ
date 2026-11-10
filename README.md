# NodeTrail v2

**Gia sư AI biết bạn đang ở đâu và dẫn bạn đi tiếp.** Linh vật: **Sena**, chú khỉ đồng hành học tập.

Người học nêu một mục tiêu ("Tôi muốn học Python") hoặc tải lên một tài liệu. NodeTrail dựng bản đồ kiến thức từ
giáo trình mở, xếp trình độ, rồi chạy vòng lặp **đánh giá → học → luyện tập → điều chỉnh → ôn tập**. Mọi giải thích
đều có trích dẫn nguồn.

## Nguyên tắc: AI giải thích, bộ máy quyết định

- **Bộ máy học tập** (hàm thuần, có kiểm thử) quyết định học gì tiếp: BKT đo mức nắm vững từng khái niệm, luật trên
  đồ thị tiên quyết xếp trình độ và truy ngược gốc lỗ hổng, FSRS lên lịch ôn. Mỗi quyết định có dấu vết bằng tiếng
  Việt (bảng «Vì sao?»).
- **Mô hình ngôn ngữ** chỉ tạo nội dung và giải thích, luôn kèm trích dẫn.
- **Cổng kiểm chứng:** một mô hình khác họ trả lời mù từ đoạn đã trích; câu chưa qua không được hiển thị. Cổng giảm
  lỗi chứ không loại hết, nên duyệt của giáo viên và số đo tỉ lệ bắt lỗi nằm trong lộ trình.

## Lộ trình v2

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| M0 | Kho nguồn có cấu trúc: sách OpenStax lấy qua git, giấy phép và thứ tự chương đọc từ siêu dữ liệu | Đã có mã và kiểm thử; chưa lập chỉ mục bằng TEI |
| M1 | Deep Research dựa trên danh mục nguồn, rồi mới đến web | Chưa làm |
| M2 | Vòng học thật qua giao diện, không dùng dữ liệu mẫu | Chưa làm |
| M3 | Đo cổng kiểm chứng, truy xuất, xếp trình độ; hàng đợi giáo viên duyệt | Chưa làm |
| M4 | Giáo viên AI giảng theo slide và bảng trắng, do bộ máy điều khiển | Chưa làm |

Chi tiết: [`docs/v2/plan-m0-m1.md`](docs/v2/plan-m0-m1.md).

## Hiện trạng trung thực

- 1.557 kiểm thử API đạt, 20 bị bỏ qua (đo cục bộ, 2026-11-10); ruff và mypy sạch. 20 kiểm thử bỏ qua so sánh
  hợp đồng với một commit của repo nhóm, commit đó không có trong repo này. Kiểm thử web chưa chạy lại ở đây.
- Giao diện web còn dùng dữ liệu mẫu ở một số bước, chưa nối hết với bộ máy thật.
- Chưa đo: tỉ lệ bắt lỗi của cổng kiểm chứng, độ trúng truy xuất, hiệu quả học. Xếp trình độ trên nhiễu mô phỏng
  đúng khoảng 56 đến 64% (mục tiêu 90%).
- Tham số BKT là giá trị khởi đầu theo tài liệu, chưa hiệu chỉnh trên dữ liệu người học thật.

## Chạy thử

Cần Docker, Python 3.12 với `uv`, Node.js với `pnpm`.

```bash
docker compose up -d --wait db
```

```bash
cd apps/api && uv sync && uv run python -m app.migrate && uv run pytest -q
```

Lấy sách vào thư viện (M0), rồi lập chỉ mục khi có máy chủ TEI (`docker/TEI.md`):

```bash
cd apps/api && uv run python -m app.sources.fetch ../../data/sources/catalog.yaml --out ../../data/library-v2
```

```bash
cd apps/api && uv run python -m app.rag.library ../../data/library-v2 --tei-url http://localhost:8080 --build-index
```

Sao chép `.env.example` thành `.env` và tự điền khóa; không commit tệp này.

## Nguồn gốc và ghi công

Dự án tiếp nối bản dựng NodeTrail của đội **Sena Empire** trong cuộc thi hackathon 2026 (5 thành viên, repo nhóm
`thienandinh29/SenaEmpire36`, đã đóng băng). Mã kế thừa từ bản đó là công sức của cả đội; tài liệu cuộc thi nằm
trong [`docs/archive/contest-2026/`](docs/archive/contest-2026/).

Giáo trình trong danh mục là sách mở của OpenStax (CC BY-NC-SA 4.0): dùng cho học tập, không thương mại.

## Giấy phép

- **Mã nguồn** (mọi thứ ngoài `data/`): [Apache-2.0](LICENSE). Xem thêm [NOTICE](NOTICE).
- **Dữ liệu** (`data/`): [CC BY-NC-SA 4.0](data/LICENSE.md), vì một phần dữ liệu phát sinh từ giáo trình có cùng giấy phép.
  Dữ liệu này không dùng cho mục đích thương mại; mã thì dùng được.

Cả đội Sena Empire đã đồng ý lựa chọn này (theo lời chủ repo, 2026-11-10; chưa có văn bản xác nhận trong repo).
