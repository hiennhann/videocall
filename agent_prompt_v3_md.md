# AGENT PROMPT v3 – Hướng dẫn phát triển & Câu lệnh thực thi (ConnectV)

> Tài liệu này tổng hợp các quy tắc làm việc, nguyên tắc kiến trúc, quyết định thiết kế (`D25–D36`) và danh sách câu lệnh gợi ý từ `docs_v3/extend.md` và `docs_v3/ui.md`.
> *(Lưu ý: Bạn có nhắc đến 3 file nhưng hiện tại hệ thống mới nhận được 2 file là `ui.md` và `extend.md`. Nếu bạn muốn bổ sung thêm nội dung từ file thứ 3 — ví dụ `idea.md` hoặc `AGENT_PROMPT.md` gốc — hãy tải lên để tôi cập nhật tiếp vào file này).*

---

## Phần 1: Nguyên tắc cốt lõi & Quy tắc bắt buộc cho Agent

Khi thực hiện bất kỳ bước nào dưới đây, agent **bắt buộc** tuân thủ các quy tắc sau:

1. **Quy trình làm việc:**
   - **Thiết kế xong mới code:** Luôn trình bày kế hoạch triển khai chi tiết (các file sẽ tạo/sửa, schema, API, luồng xử lý) trước khi viết dòng code đầu tiên.
   - **Tài liệu là bản sống:** Nếu trong quá trình code có thay đổi so với đặc tả, phải cập nhật lại `docs/` và `docs_v3/` trong cùng một commit.
   - **Phân tầng rõ ràng (Backend):** Tuân thủ luồng `api/realtime → services → models`. Mọi kiểm tra quyền hạn phải nằm ở tầng `services`, không tin tưởng dữ liệu từ client.

2. **Kiến trúc kỹ thuật đã chốt (Không thay đổi):**
   - **Client Web người dùng:** HTML/CSS/JS thuần (ES Modules), **không dùng React/Vue hay bất kỳ bước build nào** (`D21`, `D33`).
   - **Trang quản trị (Admin):** Jinja2 + HTMX lưu cục bộ (không nạp CDN) (`D17`).
   - **Cơ sở dữ liệu & Migration:** Tạo migration dần theo từng bước (`0009` đến `0013`). Đọc lại bản autogenerate của Alembic, viết tay `downgrade()`, index một phần (`WHERE ...`) và ràng buộc `CHECK`.

3. **Bảo mật, Quyền riêng tư & An toàn dữ liệu:**
   - **Chống XSS:** Mọi dữ liệu từ người dùng (tên, tin nhắn, tên phòng) **bắt buộc gán bằng `textContent`**, tuyệt đối không dùng `innerHTML`.
   - **CSP chặt chẽ:** `script-src 'self'`, `img-src 'self' data:`, `font-src 'self'`. Phông chữ (Inter `.woff2`), biểu tượng (`sprite.svg`) và HTMX phải tự lưu cục bộ trong dự án.
   - **Xử lý ảnh đại diện (Avatar):** Chỉ nhận JPEG, PNG, WebP (kiểm tra nội dung thực bằng Pillow), **từ chối SVG**, giới hạn kích thước & điểm ảnh, xóa toàn bộ metadata EXIF, xử lý qua thread pool với semaphore nhỏ (`<= 2`) để bảo vệ RAM (`D31`).
   - **Chống dò tài khoản & Làm phiền:** Tìm bạn bằng email khớp chính xác; kết quả rỗng giống nhau cho cả "không tồn tại" và "bị ẩn" (`D26`). Từ chối lời mời kết bạn im lặng; từ chối lời mời gọi có phản hồi tức thời (`D27`).
   - **Quyền riêng tư tin nhắn:** Admin không có API đọc tin nhắn riêng (`D28`). Không ghi nội dung tin nhắn vào log.

4. **Quy tắc Giao diện & Design System (`ui.md`):**
   - **Một nguồn màu duy nhất:** Toàn bộ màu sắc khai báo bằng biến CSS trong `client/css/tokens.css` (hỗ trợ cả 2 chủ đề `light` cho người dùng và `dark` cho admin qua thuộc tính `data-theme`) (`D35`).
   - **Trung thực với dữ liệu (`D34`):** Mockup chỉ là hướng thị giác. Các tính năng chưa có backend (Lịch họp, Ghi hình, Transcript giọng nói, Băng thông phòng chi tiết, E2E) phải **ẩn đi** hoặc thay bằng dữ liệu thật hiện có, tuyệt đối không làm giả số liệu.
   - **Khả năng tiếp cận (A11y):** Hỗ trợ điều hướng bàn phím (`Tab`, khóa focus modal, `Esc`), tương phản chữ thường `≥ 4,5:1`, trạng thái không chỉ truyền đạt bằng màu sắc, tắt chuyển động khi `prefers-reduced-motion`.

---

## Phần 2: Lộ trình & Câu lệnh gợi ý cho Agent

### Giai đoạn 1: Chuẩn bị nền tảng UI (Có thể làm song song với Backend)

| Bước | Phụ thuộc | Câu lệnh gợi ý cho Agent |
|---|---|---|
| **U1** | A1 | `Thực hiện bước U1 theo docs_v3/ui.md mục 3, 4, 9.1: tạo client/css/tokens.css (hai chủ đề sáng/tối), base.css, components.css, icons/sprite.svg, phông chữ cục bộ và trang client/styleguide.html. Không framework, không build. Trình bày kế hoạch trước và chốt bảng màu bằng cách đối chiếu ảnh mockup.` |

---

### Giai đoạn 2: Mở rộng Backend & Realtime (`docs_v3/extend.md`)

> Cập nhật 21/11/2026. Giai đoạn 2 hoàn tất trên nhánh `feat/phase2`. Migration `0011`, `0012`, `0013` lần lượt thuộc E5, E6 và E4. Xem [hướng dẫn nghiệm thu](docs/docs_v3/phase2-completion.md).

> *Thứ tự đề xuất sau khi hoàn thành MVP (A1–A9): `E1 → E2 → E3 → E5 → E6 → E4 → E7`.*

| Bước | Phụ thuộc | Câu lệnh gợi ý cho Agent |
|---|---|---|
| **E1** | A3 | `Thực hiện bước E1 theo docs_v3/extend.md mục 3.2 và 4: viết migration 0009 (add_user_profile), mở rộng GET/PATCH /me, xây dựng PUT/DELETE /me/avatar với xử lý ảnh an toàn (Pillow, xóa EXIF, cắt 256px & 64px WebP, semaphore chống tràn RAM) và phục vụ /media/avatars. Trình bày kế hoạch trước.` |
| **E2** | E1 | `Thực hiện bước E2 theo docs_v3/extend.md mục 3.3 và 5: viết migration 0010 (create_friends: friend_requests, friendships chuẩn hóa a < b, user_blocks), API tìm kiếm email chính xác, gửi/nhận/từ chối im lặng lời mời kết bạn, danh sách bạn, chặn, rate limit và viết test đảm bảo không lộ email ẩn. Trình bày kế hoạch trước.` |
| **E3** | A4, E2 | `Thực hiện bước E3 theo docs_v3/extend.md mục 6: tạo room Socket.io user:<id>, xử lý presence_changed có độ trễ ~5s trước khi báo offline, phát sự kiện kết bạn, bộ nhớ đệm danh sách bạn trong RAM và cơ chế đồng bộ HTTP sau khi mất kết nối. Trình bày kế hoạch trước.` |
| **E5** | A4, E3 | `Thực hiện bước E5 theo docs_v3/extend.md mục 8: viết migration 0011 (create_room_invites), POST /rooms/{code}/invites, GET /invites, mở rộng sự kiện join_room hỗ trợ invite_id (vào phòng có mật khẩu không cần nhập mật khẩu), job hết hạn lời mời và viết test invite của người khác bị từ chối. Trình bày kế hoạch trước.` |
| **E6** | A4 (A8) | `Thực hiện bước E6 theo docs_v3/extend.md mục 3.6 và 9: viết migration 0012 (create_call_participants), ghi nhận lịch sử khi vào/ra phòng ở luồng nền, tự động đóng các dòng treo khi app khởi động lại, API GET/DELETE /me/call-history và xuất nhật ký chat (text/plain). Trình bày kế hoạch trước.` |
| **E4** | E3 | `Thực hiện bước E4 theo docs_v3/extend.md mục 3.4 và 7: viết migration 0013 (create_direct_messages: conversations, direct_messages), xử lý socket dm_send có ack và chống trùng qua client_msg_id, dm_read, dm_typing, API lịch sử theo con trỏ và xóa mềm tin nhắn. Trình bày kế hoạch trước.` |
| **E7** | A6 | `Thực hiện bước E7 theo docs_v3/extend.md mục 11 và 12: mở rộng API admin (/admin/users/{id}, gỡ avatar vi phạm, lịch sử cuộc gọi cấp phòng), thêm cấu hình mới vào SettingsSchema + /config/public và ghi audit log user.avatar_remove. Trình bày kế hoạch trước.` |

---

### Giai đoạn 3: Xây dựng & Tích hợp Giao diện người dùng và Quản trị (`docs_v3/ui.md`)

> *Thứ tự đề xuất: `U1 → U2 → U3 → U4`, sau đó làm `U5`, `U6` khi các bước `E` tương ứng hoàn tất, và chốt lại bằng `U7`.*

| Bước | Phụ thuộc | Câu lệnh gợi ý cho Agent |
|---|---|---|
| **U2** | A2, A4, U1 | `Thực hiện bước U2 theo docs_v3/ui.md mục 5, 6.1–6.3: đăng nhập/đăng ký/khách, Trang chủ, Phòng của tôi, các trang Vào/Tạo phòng trên URL riêng. Dùng textContent cho dữ liệu người dùng. Trình bày kế hoạch trước.` |
| **U3** | A5 (A9), U1 | `Thực hiện bước U3 theo docs_v3/ui.md mục 6.4: thiết kế lại màn hình chờ (lobby) và room.html theo phong cách mới gồm lưới video tự co giãn, thanh điều khiển đáy, khung bên phải 3 tab (Chat/Người/Mời) và bong bóng chỉ số mạng (RTT, packet loss, bitrate). Trình bày kế hoạch trước.` |
| **U4** | A6, U1 | `Thực hiện bước U4 theo docs_v3/ui.md mục 7 và 9.3: xây dựng base_admin.html (chủ đề tối dùng chung tokens.css), các trang Tổng quan, Phòng trực tiếp, Thành viên, Cấu hình & Bảo mật với HTMX lưu cục bộ cập nhật mỗi 5 giây và tuân thủ CSP chặt. Trình bày kế hoạch trước.` |
| **U5** | E2–E5, U2 | `Thực hiện bước U5 theo docs_v3/ui.md mục 6.5–6.8: xây dựng màn hình Bạn bè, Tin nhắn (1-1), thẻ thông báo lời mời gọi nổi có đếm ngược, chuông thông báo và hộp thoại/tab Mời bạn vào phòng; kết nối toàn bộ sự kiện Socket.io vào store. Chỉ thực hiện khi E2–E5 đã xong. Trình bày kế hoạch trước.` |
| **U6** | E1, E6, E7, U2, U4 | `Thực hiện bước U6 theo docs_v3/ui.md mục 6.9–6.10 và 7.3: xây dựng màn hình Lịch sử cuộc gọi (kèm ngăn kéo chi tiết, tải nhật ký chat), Hồ sơ & Cài đặt (upload avatar, quyền riêng tư, đổi theme) và trang admin Báo cáo & Phân tích với biểu đồ SVG do server dựng. Trình bày kế hoạch trước.` |
| **U7** | U2–U6 | `Thực hiện bước U7 theo docs_v3/ui.md mục 5.4 và 10: hoàn thiện đáp ứng đa kích thước màn hình (desktop, tablet, thanh điều hướng đáy cho mobile), kiểm tra khả năng tiếp cận (bàn phím, tương phản màu, aria-live), kiểm tra trực quan trên 2 trình duyệt và xuất báo cáo điểm Lighthouse thật. Trình bày kế hoạch trước.` |

---

## Phần 3: Tiêu chí nghiệm thu (Definition of Done) cho mỗi bước

- **Backend (`E1–E7`):** Có unit test & integration test tương ứng; chạy qua `alembic check` và `alembic upgrade/downgrade`; không có lỗi lint/type; cập nhật tài liệu `docs/` liên quan.
- **Frontend (`U1–U7`):** Chạy ổn định trên ít nhất 2 trình duyệt khác nhau ở 3 độ rộng màn hình (rộng `≥ 1200px`, vừa `768–1199px`, điện thoại `< 768px`); không có lỗi trong console hoặc vi phạm CSP; vượt qua kiểm tra điều hướng bàn phím; đính kèm ảnh chụp màn hình vào báo cáo hoàn thành bước.
