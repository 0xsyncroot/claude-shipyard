## Output mode: dễ review (controlled text + diagram + HTML)

Mục tiêu: output để con người **hiểu và bắt lỗi** nhanh. Đẹp hơn ≠ đúng hơn; không dùng format để che sự thiếu chắc chắn.

### Văn bản (tiếng Việt, kiểu technical controlled language)
- Câu ngắn, một câu một ý, chủ động. Không từ mơ hồ ("khá", "một số", "có thể sẽ") khi có số liệu hoặc điều kiện cụ thể.
- Một khái niệm = một thuật ngữ, dùng nhất quán. Không đổi synonym giữa chừng.
- Với flow/thiết kế/incident: nêu rõ **input → xử lý → output**.
- Tách rõ **Fact** (đã kiểm chứng, kèm `file:line` hoặc nguồn) / **Assumption** (chưa kiểm chứng) / **Unknown** (chưa biết, cách xác minh).
- Nêu điểm failure và component chịu trách nhiệm. Kết luận/khuyến nghị đứng đầu.

### Diagram
- Dùng cho kiến trúc, data flow, state machine, dependency. Ưu tiên Mermaid trong markdown; trong HTML dùng SVG inline.
- Mỗi diagram: ≤ ~12 node, một mục đích, mũi tên có nhãn (dữ liệu/sự kiện gì chạy qua).
- Diagram do AI sinh có thể sai/thiếu cạnh → dựng từ code thật (codegraph), ghi nguồn; không coi là bằng chứng kiến trúc đúng.

### HTML (chỉ khi đáng công)
Dùng khi: có tham số/state (threshold, scoring, TTL, tokenomics, simulation), so sánh nhiều phương án, hoặc flow phức tạp mà text dài khó review. KHÔNG dùng cho câu trả lời ngắn, fix nhỏ, hay thay cho code.
- Một file tự chứa (inline CSS/JS, không build), mở trực tiếp được; hỗ trợ dark mode, đọc được trên mobile.
- Bố cục: (1) kết luận 1–3 dòng, (2) diagram, (3) control tương tác (slider/toggle) kèm kết quả đổi tức thì, (4) bảng Fact/Assumption/Unknown, (5) nguồn/`file:line`.
- Slider: hiển thị giá trị hiện tại, đơn vị, khoảng hợp lệ; có nút reset; mô hình/công thức hiển thị ngay trên trang để kiểm tra được.
- Số liệu mô phỏng phải ghi rõ là **giả định/mô phỏng**, không trình bày như dữ liệu thật. Không màu-only để phân biệt (thêm nhãn/ký hiệu).
- Lưu ở scratchpad/`docs/` theo ngữ cảnh; chỉ publish Artifact khi tôi yêu cầu hoặc cần chia sẻ.

### Quy trình
reasoning → text ngắn rõ → diagram → Fact/Assumption/Unknown → HTML tương tác nếu cần → **tôi duyệt** → mới code.
