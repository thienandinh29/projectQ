# Đề xuất dự án: NodeTrail – Gói tiếng Anh

Nov 14, 2026 · @Anthien

## Tóm tắt

Mình đề xuất xây **gói tiếng Anh** chạy trên engine học thích ứng NodeTrail (projectQ). Gói này giúp người học Việt Nam luyện phát âm, viết và đi theo lộ trình CEFR (B2, C1) hoặc IELTS mà không phải trả phí như các app thương mại.

- **Cho ai:** trước hết là chính mình (đang ôn IELTS, mục tiêu 6.5), sau đó là bạn bè và người thân, dùng miễn phí.
- **Khác biệt:** engine quyết định học gì tiếp (BKT, FSRS), lộ trình chỉ hiện các node trọng yếu, các mô hình ML nhỏ lo chấm phát âm và chấm Writing, LLM chỉ giải thích và viết mẫu. Chi phí thấp, kết quả ổn định hơn chatbot thuần.
- **Phạm vi:** đủ 4 kỹ năng, lộ trình từ A2 đến C1 theo CEFR, kèm phần luyện riêng cho IELTS.
- **Thời gian:** khoảng 7 tháng nếu làm một mình, 3–4 tháng nếu có thêm 2 người, chia 5 giai đoạn, mỗi giai đoạn có cổng đo trước khi đi tiếp.

## Vấn đề và bối cảnh

Người học tiếng Anh ở Việt Nam đang kẹt giữa hai lựa chọn: app chuyên sâu nhưng tốn phí, hoặc chatbot miễn phí nhưng không có lộ trình.

- **App luyện phát âm và chấm bài** thường thu phí theo tháng, không phải ai cũng trả được lâu dài.
- **Dán bài vào chatbot** thì được nhận xét hay, nhưng điểm dao động giữa các lần chấm, không nhớ lỗi cũ, không biết người học đang ở đâu và cần học gì tiếp.
- **Lỗi đặc thù của người Việt** (âm cuối, /θ/ /ð/, mạo từ, hòa hợp chủ–vị) ít được luyện có hệ thống.

NodeTrail đã có sẵn phần khó nhất: một engine theo dõi mức thành thạo từng khái niệm và lên lịch ôn tập. Tiếng Anh là môn đầu tiên phù hợp để chứng minh engine này chạy được với người dùng thật.

## Mục tiêu, người dùng và phạm vi

Mục tiêu là một app học tiếng Anh toàn diện, nhưng làm theo từng lát cắt và bắt đầu từ những gì chính mình dùng hằng ngày.

**Người dùng:**

1. Chính mình, ôn IELTS (hiện khoảng 5.0 Reading/Listening, 4.5 Writing).
2. Bạn bè, người thân muốn đạt B2 hoặc C1, dùng miễn phí.
3. Về sau: học sinh và sinh viên nói chung.

**Trong phạm vi:** lộ trình CEFR A2–C1 kèm test đầu vào; từ vựng và ngữ pháp; luyện phát âm; chấm và sửa Writing Task 1 và 2; Listening và Reading theo cấp độ; Speaking Part 1–3; ôn tập theo lịch.

**Ngoài phạm vi:** app di động riêng (bản web dùng được trên điện thoại), thu phí, môn học khác ngoài tiếng Anh, và mọi cam kết về điểm thi chính thức.

## Giải pháp và kiến trúc

NodeTrail là engine chung, tiếng Anh là gói môn học đầu tiên cắm vào đó. Gói tiếng Anh chỉ cung cấp nội dung, mô hình chấm và prompt riêng; mọi quyết định học gì tiếp do engine đưa ra.

&#91;embedded content: kiến trúc · gói tiếng Anh trên engine chung\]

Phần tô màu là việc cần làm mới. Engine bên dưới đã có, nên sau này thêm môn khác chỉ cần thêm một gói.

## Các thành phần chính

Năm thành phần dưới đây đều theo cùng một nguyên tắc: công cụ và mô hình nhỏ lo việc đo đúng sai, LLM lo việc giải thích.

### 1. Lộ trình CEFR và test đầu vào

- **Hai lớp node.** Node trọng yếu là cột mốc hiển thị trên lộ trình, ví dụ "Câu điều kiện", "Mệnh đề quan hệ". Giữa hai cột mốc là các node ẩn nhỏ hơn. Mọi node đều gắn cấp CEFR (nguồn: CEFR-J wordlist, tham khảo English Vocabulary Profile và English Grammar Profile).
- **Đồ thị nông.** Quan hệ tiên quyết đi theo tầng CEFR (A2 → B1 → B2 → C1). Chỉ thêm cạnh tường minh cho các chuỗi hiển nhiên như câu điều kiện loại 1 → 2 → 3. Từ vựng không cần cạnh tiên quyết, chỉ cần cấp CEFR và FSRS. Cạnh nào dữ liệu cho thấy sai (nhiều người thạo B mà chưa thạo A) thì bỏ.
- **Qua cột mốc:** các node ẩn phía trước được coi là đã biết. Mỗi cột mốc có 3–4 câu, mỗi câu chạm một kỹ năng con khác nhau, để đoán trúng một câu không đủ để qua.
- **Không qua cột mốc:** mở các node ẩn giữa cột mốc đó và cột mốc trước, hỏi nhanh 1–2 câu mỗi node để tìm đúng chỗ hổng, chỉ học node đó, rồi quay lại cột mốc. Repo đã có logic này trong `remediation.py`.
- **Node ẩn vẫn nhận bằng chứng từ nơi khác.** Đã qua cột mốc "Mạo từ" nhưng bài viết vẫn sai mạo từ liên tục thì node ẩn tương ứng tự mở lại.
- **Test đầu vào** dạng adaptive theo tầng, khoảng 15–20 phút, dừng khi engine đã đủ chắc. Người dùng chọn mục tiêu (B2, C1), engine lấy các cột mốc chưa qua và xếp theo tầng.
- **Soạn nội dung theo nhu cầu.** Cột mốc soạn kỹ trước. Node ẩn soạn dần, ưu tiên những cột mốc mà người dùng vấp nhiều nhất.

### 2. Luyện phát âm

- **Pipeline:** wav2vec2 nhận dạng âm vị → forced alignment với câu mẫu → chấm GOP (Goodness of Pronunciation).
- **Chỉ chấm 8–10 âm mục tiêu** mà người Việt hay sai (âm cuối, /θ/, /ð/, /ʃ/ và /s/...), bằng câu ngắn soạn sẵn. Không chấm mọi âm vị.
- **Ngưỡng thiên về dễ dãi:** chỉ tô đỏ khi mô hình rất chắc. Bỏ sót một lỗi ít hại hơn nhiều so với báo sai một âm đọc đúng.
- **Cổng chất lượng ghi âm:** quá ồn hoặc quá nhỏ thì yêu cầu ghi lại, không chấm.
- **Đo trước khi bật tô đỏ:** đo tỉ lệ báo sai trên 50–100 câu tự ghi. Chưa đạt ngưỡng thì chỉ bật chế độ nghe giọng mình cạnh bản chuẩn.
- **Fine-tune giọng Việt** bằng speechocean762, L2-ARCTIC và ghi âm tự thu (có đồng ý của người ghi).
- **Nối với BKT:** mỗi âm vị là một node. Tỉ lệ báo sai và bỏ sót đo được dùng làm P(S) và P(G) cho các node phát âm, nên hai phép đo này phục vụ luôn cho engine.

### 3. Chấm Writing

- **NLP** đếm và tìm lỗi: LanguageTool cho ngữ pháp, spaCy cho độ phức tạp câu, wordlist CEFR cho cấp từ vựng, đếm từ nối và cách chia đoạn.
- **ERRANT** gom lỗi ngữ pháp thành khoảng 25 loại (mạo từ, giới từ, thì động từ, hòa hợp chủ–vị...). Một bảng ánh xạ viết tay đưa các loại này về khoảng 15–20 node. Lỗi không ánh xạ được vẫn hiển thị cho người học nhưng không cập nhật BKT: thà bỏ sót còn hơn cập nhật sai.
- **Mô hình chấm nhỏ** dự đoán band Task 2. Bắt đầu từ các mô hình có sẵn trên Hugging Face (DistilBERT, DeBERTa-v3), chọn cái khớp nhất trên bộ eval rồi fine-tune thêm. Task 1 chỉ dùng NLP và LLM cho đến khi có đủ dữ liệu.
- **LLM** đọc bài kèm bảng phân tích, chấm Task Response, trích câu làm bằng chứng và viết nhận xét. Điểm hiển thị dạng khoảng, ví dụ "ước lượng 5.5–6.0".
- **Chạy qua hàng đợi nền** (repo đã có `jobs/worker`), vì chấm bài viết không cần trả kết quả tức thì.

### 4. Vòng sửa lỗi và viết lại

1. Mỗi lỗi đã ánh xạ được đưa vào BKT qua node tương ứng. Mỗi bài chỉ tập trung 2–3 lỗi quan trọng nhất.
2. Gợi ý trước, đáp án sau: người học tự sửa câu sai của mình.
3. LLM viết lại đoạn văn **cao hơn đúng 1 band**, giữ ý của người học, tô màu và giải thích từng chỗ sửa.
4. Bản viết lại được kiểm tra: không vượt cấp CEFR mục tiêu, không còn lỗi ngữ pháp, mô hình chấm cho điểm cao hơn. Không đạt thì sinh lại.
5. Cụm từ hay thành thẻ FSRS. Bài luyện thêm lấy từ kho đã kiểm duyệt, LLM chỉ sinh mới khi kho thiếu.
6. Bài viết sau là thước đo thật: lỗi cũ có giảm không.

### 5. Nghe, Đọc và Nói

- **Listening:** bài nghe theo cấp CEFR, giọng đọc từ TTS nhiều accent hoặc nguồn license mở. Câu hỏi sinh trước, duyệt rồi mới đưa vào kho, mỗi câu gắn một node như nghe số liệu hay nghe ý chính.
- **Reading:** văn bản license mở, gắn cấp bằng wordlist CEFR, có các dạng câu IELTS như True/False/Not Given và matching headings.
- **Speaking Part 1–3:** Whisper chép lời. Grammar và Lexical dùng lại pipeline của Writing, Pronunciation lấy từ mục 2, cộng thêm số đo fluency (tốc độ nói, quãng ngừng). Band chỉ hiện dạng khoảng ước lượng.
- **Không đưa đề Cambridge vào app** vì bản quyền. Người học vẫn luyện đề thật bên ngoài, app dùng kết quả đó để điều chỉnh lộ trình.

## Hiện trạng repo

Engine lõi đã có và được test kỹ, nhưng chưa có nội dung tiếng Anh và chưa có người dùng thật. Số liệu theo README của [projectQ](https://github.com/thienandinh29/projectQ) (chạy local ngày 10/11/2026):

| Hạng mục | Tình trạng |
| --- | --- |
| Test API | 1.557 pass, 20 skip; Ruff và mypy sạch |
| BKT, FSRS, placement | Có code; tham số BKT là giá trị mặc định trong sách, chưa tinh chỉnh |
| Độ chính xác placement | Khoảng 56–64% trên dữ liệu mô phỏng với ít câu hỏi; mục tiêu 90%, tăng dần khi hỏi nhiều câu hơn |
| LLM gateway | DeepSeek sinh nội dung, Gemini kiểm chứng; phân tầng free/pro |
| Thư viện nguồn | OpenStax; chưa index xong bằng TEI; chưa có giáo trình tiếng Anh |
| Web UI | Một số bước vẫn dùng dữ liệu mẫu |
| Chưa đo | Tỉ lệ bắt lỗi của cổng kiểm chứng, độ chính xác retrieval, hiệu quả học |

## Chi phí và vận hành

Ước lượng thô cho vài chục người dùng: vài đô mỗi tháng tiền LLM, cộng một máy chủ CPU khoảng 8 GB RAM (đủ cho wav2vec2 bản nhỏ, LanguageTool và mô hình chấm). Phát âm chấm trực tiếp với câu dưới 10 giây; Writing và Speaking chạy qua hàng đợi nền. Các con số này cần đo lại khi có người dùng thật.

**Đã có trong repo:**

- Engine (BKT, FSRS, placement) không gọi LLM, nên quyết định học gì tiếp là miễn phí.
- Model rẻ (DeepSeek) cho phần sinh nội dung.
- Cache theo topic: cùng một mục tiêu thì dùng lại map và câu hỏi đã sinh. Hint cũng được cache.
- Giới hạn output 4096 token, phần thinking tắt hoặc ở mức thấp; deep research có trần 15 lần search, 12 lần đọc, 8 phút.

**Cần làm trước khi mở cho người khác dùng:**

- [ ] Giới hạn lượt gọi LLM mỗi người mỗi ngày, nhất là chat với Sena và chấm Writing.
- [ ] Theo dõi token theo ngày, đặt trần chi phí; vượt trần thì chuyển sang chế độ chỉ ôn tập.
- [ ] Chuẩn hóa chuỗi mục tiêu trước khi so cache (hoa/thường, khoảng trắng).
- [ ] Giữ phần đầu prompt cố định để tận dụng cơ chế cache của DeepSeek.
- [ ] Chính sách dữ liệu giọng nói: nói rõ có lưu không, cho phép xóa, hỏi ý trước khi dùng để fine-tune.

Không fine-tune LLM. Thay vào đó xây harness riêng cho tiếng Anh (prompt theo việc, tool, nguồn RAG, schema, bộ eval) và chỉ fine-tune các mô hình nhỏ cho phát âm và chấm Writing.

## Đánh giá và chỉ số thành công

Dự án chỉ được coi là thành công khi có số đo, không phải khi có đủ tính năng. Các ngưỡng dưới đây là mục tiêu ban đầu, sẽ chỉnh lại sau khi đo lần đầu.

| Thành phần | Chỉ số | Dữ liệu để đo | Mục tiêu ban đầu |
| --- | --- | --- | --- |
| Placement | Đường cong độ chính xác theo số câu hỏi | Mô phỏng hiện có trong repo | ≥ 90% với ≤ 20 câu |
| Cột mốc | Tỉ lệ người qua cột mốc nhưng vẫn sai node ẩn trong bài viết | Log của app | Càng thấp càng tốt; ghi baseline trước |
| Ánh xạ lỗi | Tỉ lệ ánh xạ đúng node | 100 lỗi kiểm tra bằng tay | ≥ 90% |
| BKT | Tham số fit theo nhóm so với mặc định | Dữ liệu giữ lại (`bkt_fit.py`) | Thắng mặc định |
| Phát âm | Tỉ lệ báo sai (âm đọc đúng bị tô đỏ) | 50–100 câu tự ghi | ≤ 10% |
| Phát âm | Tương quan (PCC) với điểm người chấm | speechocean762 | Ghi baseline, tăng sau fine-tune |
| Chấm Writing | QWK giữa máy và giám khảo | 50–100 bài mẫu chính thức có band (IELTS, British Council, IDP, sách Cambridge) | ≥ 0.7 |
| Chấm Writing | Độ ổn định: cùng bài chấm 5 lần | Bộ eval trên | Lệch tối đa 0.5 band |
| Hiệu quả học | Lỗi cũ giảm ở bài viết sau; điểm thi thật so với điểm app | Người dùng thử; kết quả thi của chính mình | Xu hướng giảm rõ sau 4 tuần dùng |
| Sử dụng | Số người còn dùng sau 2 tuần | Log của app | ≥ 5/10 người dùng thử |

Bài mẫu chính thức chỉ dùng để đo, không đưa vào app vì có bản quyền.

## Lộ trình triển khai

Bản hoàn thiện chia 5 giai đoạn, tổng cộng khoảng 7 tháng nếu làm một mình với 3–4 tiếng mỗi ngày. Mỗi giai đoạn chỉ kết thúc khi đạt cổng đo của nó.

&#91;embedded content: lộ trình · 4 tuần MVP, 1 cổng, giai đoạn mở rộng\]

Thứ tự đi từ nền tảng đến kỹ năng: knowledge map và placement phải vững trước, vì mọi kỹ năng sau đều đổ bằng chứng vào đó. Xong giai đoạn nào thì giai đoạn đó dùng được ngay cho việc ôn thi của chính mình. Có thêm 2 người thì giai đoạn 2–4 chạy song song, rút còn khoảng 3–4 tháng.

## Nhân sự và phân vai

Hiện mình làm một mình. Có thêm 1–2 người sẽ rút bản đầy đủ từ khoảng 5–7 tháng xuống 3–4 tháng.

| Vai | Phụ trách | Cần biết |
| --- | --- | --- |
| Engine và ML (mình) | BKT, placement, mô hình phát âm, mô hình chấm Writing, harness LLM | Python, ML |
| Nội dung tiếng Anh | Gắn nhãn CEFR, viết và duyệt câu hỏi theo template, soạn bộ eval | Tiếng Anh tốt; không cần code nhiều |
| Frontend và deploy | UI vòng học, ghi âm trên web, tài khoản, rate limit, server | TypeScript, Docker |
| Người dùng thử (ai cũng làm được) | Dùng hằng ngày, báo lỗi, đóng góp ghi âm và bài viết | Không yêu cầu |

Người mới không cần hiểu toàn bộ lõi: mỗi vai có đầu vào và đầu ra rõ ràng, dựa trên `specs/` và các API đã có. Quyền sở hữu và cách chia nếu sau này thương mại hóa sẽ thống nhất ngay từ đầu.

## Rủi ro và cách giảm thiểu

| Rủi ro | Ảnh hưởng | Cách giảm |
| --- | --- | --- |
| Ánh xạ lỗi sang node sai | BKT cập nhật sai, lộ trình lệch | ERRANT gom lỗi về \~25 loại, bảng ánh xạ viết tay; lỗi không ánh xạ được thì không cập nhật BKT |
| Cây tiên quyết sai do thiếu chuyên môn sư phạm | Placement và lộ trình sai dây chuyền | Đồ thị nông theo tầng CEFR; chi tiết nằm cục bộ giữa hai cột mốc; bỏ cạnh mà dữ liệu bác bỏ |
| Qua cột mốc nhờ đoán trúng | Node ẩn bị coi là đã biết | 3–4 câu mỗi cột mốc; node ẩn tự mở lại khi bài viết còn sai |
| Phát âm báo sai nhiều (giọng Việt, micro, tạp âm) | Người học ức chế, bỏ app | Chỉ 8–10 âm mục tiêu, ngưỡng dễ dãi, cổng chất lượng ghi âm, đo báo sai trước khi bật tô đỏ, fine-tune giọng Việt |
| Máy chủ quá tải khi chạy nhiều mô hình | Phản hồi chậm hàng chục giây | wav2vec2 bản nhỏ hoặc lượng tử hóa; Writing, Speaking qua hàng đợi nền; máy \~8 GB RAM, đo latency thật |
| Tham số BKT mặc định (cold-start) | Đánh giá sai mức thành thạo | Tham số theo nhóm loại câu hỏi; P(S), P(G) của phát âm lấy từ tỉ lệ báo sai đo được; fit lại khi có dữ liệu |
| Điểm chấm Writing sai lệch | Người học tin vào điểm không đúng | Hiển thị khoảng điểm; đo QWK; đánh dấu "không chắc" khi các mô hình lệch quá 1 band |
| Dự án kéo dài \~7 tháng và lấn thời gian ôn IELTS | Mất động lực, trượt mục tiêu 6.5 | Khoảng 70% thời gian cho ôn thi; mỗi giai đoạn có cổng đo, xong giai đoạn nào dùng được ngay giai đoạn đó |
| License nội dung | `data/` dùng CC BY-NC-SA, không được thương mại hóa | Miễn phí cho bạn bè thì ổn; nếu thu phí sau này thì tự soạn hoặc dùng nguồn license thoáng |
| Chi phí LLM vượt dự kiến | Không đủ tiền duy trì | Rate limit, trần chi phí theo ngày, kho câu hỏi sinh trước |
| Dữ liệu giọng nói cá nhân | Mất niềm tin người dùng | Thông báo rõ, cho xóa, xin đồng ý trước khi dùng để train |

## Câu hỏi xin góp ý

Mình rất muốn nghe ý kiến thẳng thắn, cứ comment trực tiếp vào đoạn nào bạn thấy chưa ổn.

1. Nếu được dùng miễn phí, bạn có dùng app này không? Bạn cần luyện kỹ năng nào nhất?
2. Cách lộ trình chỉ hiện cột mốc, ẩn các node nhỏ, có dễ theo dõi hơn không? Bạn muốn thấy tiến độ chi tiết đến mức nào?
3. Test đầu vào 15–20 phút có quá dài không?
4. Điểm hiển thị dạng khoảng (5.5–6.0) có dễ hiểu và đáng tin hơn một con số không?
5. Bạn có sẵn lòng đóng góp bài viết hoặc ghi âm để cải thiện mô hình không?
6. Bạn có muốn tham gia dự án không, và ở vai nào (nội dung, frontend, dùng thử)?
7. Bạn thấy rủi ro nào lớn nhất mà đề xuất này đang bỏ qua?

## Nguồn tham khảo

- [projectQ (NodeTrail v2)](https://github.com/thienandinh29/projectQ)
- [KevSun/IELTS\_essay\_scoring](https://huggingface.co/KevSun/IELTS_essay_scoring)
- [star092304/ielts-writing-task2-debertav3base](https://huggingface.co/star092304/ielts-writing-task2-debertav3base)
- [KevSun/Engessay\_grading\_ML (ELLIPSE)](https://huggingface.co/KevSun/Engessay_grading_ML)
- [Mitigating Bias in AES for ESL Learners](https://arxiv.org/pdf/2601.16724)
