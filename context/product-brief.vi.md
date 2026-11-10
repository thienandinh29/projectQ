# NodeTrail — Product brief (original, Vietnamese)

> Source: ../Bản tóm tắt.docx

Bản ngắn 

NodeTrail: Chỉ cần bạn muốn học, Sena sẽ dẫn đường.

NodeTrail là gia sư AI cho mọi môn học. Ví dụ bạn chỉ cần nói một câu như "Tôi muốn học Python". NodeTrail dựng bản đồ kiến thức từ giáo trình uy tín, tìm ra đúng chỗ bạn hiểu nhầm, tự điều chỉnh lộ trình và nhắc bạn ôn trước khi quên. Đồng hành cùng bạn là Sena, chú khỉ dẫn đường đáng yêu.

Bản đầy đủ

Tên sản phẩm: NodeTrailLinh vật: chú khỉ SenaCâu định vị: Gia sư AI cho mọi môn học: biết bạn đang ở đâu, và dẫn bạn đi tiếp.

Vấn đề

Tỷ lệ hoàn thành trung vị của các khóa học online chỉ khoảng 12,6% (Jordan, 2015). Người tự học không biết bắt đầu từ đâu, học xong lại quên, và chatbot AI chỉ trả lời từng câu, không biết người học nên học gì tiếp. Người học không thiếu thông tin. Họ thiếu một người dẫn đường.

Giải pháp

Người học chỉ cần nói mục tiêu hoặc tải đề cương môn học lên. NodeTrail tìm giáo trình uy tín, dựng bản đồ kiến thức (Knowledge Graph), rồi dẫn người học qua một vòng lặp: đánh giá, học, luyện tập, điều chỉnh và ôn tập.

7 tính năng chính

Knowledge Graph: bản đồ khái niệm và thứ tự học, trích từ chính giáo trình. Nút càng sáng, người học càng vững.

Đánh giá đầu vào thích ứng: 10 phút để biết người học đang ở đâu.

Adaptive Quiz: câu hỏi lấy từ bài tập giáo trình, mỗi đáp án sai ứng với một hiểu nhầm cụ thể.

Lộ trình tự điều chỉnh: khi người học sai, hệ thống tìm nguyên nhân gốc và quay về phần nền tảng còn yếu.

Gia sư gợi mở (Socratic): không đưa đáp án, gợi ý từng bước, luôn trích dẫn giáo trình.

Ghi chú thông minh: ghi chú dạng khối, tự chuyển thành thẻ ôn tập.

Ôn tập trước kỳ thi: lịch ôn lập ngược từ ngày thi, 20 phút mỗi ngày.

Điểm khác biệt

Tìm nguyên nhân gốc: chatbot giải thích lại lần thứ năm, NodeTrail tìm ra vì sao bạn chưa hiểu.

Đáng tin cậy: nội dung trích xuất từ giáo trình uy tín, mọi lời giải thích đều có nguồn.

Học mọi môn: đổi mục tiêu là đổi môn, từ Python đến IELTS.

Sena đồng hành: chỉ khen khi người học thật sự hiểu bài, không thưởng cho tốc độ hay chuỗi ngày.

Công nghệ

Kiến trúc harness quanh LLM:

Learning Engine ra quyết định: Bayesian Knowledge Tracing, rule engine, FSRS, Elo.

Grader theo môn chấm bài khách quan: test case, đáp án, thang tiêu chí.

LLM + RAG chỉ đảm nhận phần giải thích, có trích dẫn.

Nền tảng: Next.js, FastAPI, Supabase + pgvector.

Tác động

Dùng cho tất cả mọi người muốn học thêm 1 thứ gì mới.

Áp dụng ngay cho sinh viên: tải đề cương môn đang học là bắt đầu.

Giảng viên và trung tâm dùng cho cả lớp, thấy rõ lớp đang yếu ở đâu.

Càng nhiều người học, NodeTrail càng rẻ hơn và dạy tốt hơn.
