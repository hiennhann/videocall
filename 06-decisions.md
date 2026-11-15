# 06. Quyết định kiến trúc (ADR) và câu hỏi còn mở

> Mỗi quyết định có: bối cảnh ngắn, lựa chọn, lý do, hệ quả. Đây là nguyên liệu trực tiếp cho phần "thiết kế và lý do" trong báo cáo.
> Trạng thái: **Đã chốt** (đã thống nhất khi trao đổi), **Đề xuất** (mình đề xuất, chờ bạn xác nhận).

## Bảng tóm tắt

| ID | Quyết định | Trạng thái |
|---|---|---|
| D01 | FastAPI + python-socketio, mount cùng một ASGI app | Đã chốt |
| D02 | Dùng Socket.io (không dùng WebSocket thuần) cho signaling | Đã chốt |
| D03 | Mesh trước, SFU (aiortc) sau | Đã chốt |
| D04 | Phân tầng `api/realtime → services → models` | Đã chốt |
| D05 | Trạng thái phòng trong RAM, sau lớp trừu tượng; chưa dùng Redis | Đã chốt |
| D06 | UUID, `timestamptz`, `varchar + CHECK` thay ENUM | Đã chốt |
| D07 | Migration tạo dần, service `migrate` riêng | Đã chốt |
| D08 | JWT access ngắn + refresh token ngẫu nhiên xoay vòng, lưu hash | Đề xuất |
| D09 | Refresh token qua body JSON ở v1 | Đã chốt |
| D10 | Chế độ khách (guest) bằng JWT không có dòng DB | Đã chốt |
| D11 | Mật khẩu hash bằng argon2id | Đề xuất |
| D12 | Kiểm tra role/`is_active` từ DB ở mỗi request | Đã chốt |
| D13 | Cấu hình vận hành trong DB, bí mật trong biến môi trường | Đã chốt |
| D14 | Credential TURN tạm thời bằng HMAC | Đã chốt |
| D15 | Socket chỉ xác thực lúc kết nối, thu hồi chủ động | Đề xuất |
| D16 | Người mới gửi offer; "perfect negotiation" cho đàm phán lại | Đề xuất |
| D17 | Admin web bằng Jinja2 + HTMX | Đã chốt |
| D18 | Caddy thay vì Nginx | Đề xuất |
| D19 | coturn dùng `network_mode: host` | Đề xuất |
| D20 | Rate limit trong bộ nhớ (slowapi) ở v1 | Đề xuất |
| D21 | Client JS thuần, không framework | Đã chốt |
| D22 | Mục tiêu độ trễ < 200 ms, không phải "0" | Đã chốt |
| D23 | Viết đầy đủ tài liệu trước khi code | Đã chốt |

---

## D01. FastAPI + python-socketio trên cùng một ASGI app
**Bối cảnh:** cần REST API và WebSocket realtime, ưu tiên Python.
**Quyết định:** FastAPI cho HTTP; `socketio.AsyncServer` bọc bằng `socketio.ASGIApp(sio, other_asgi_app=fastapi_app)`, chạy bằng Uvicorn.
**Lý do:** async end-to-end, một process phục vụ cả hai, dùng chung code service/DB.
**Hệ quả:** chung một event loop, nên **không được gọi code chặn** (hash argon2 chạy trong `run_in_executor`, thư viện DB phải là bản async).

## D02. Socket.io cho signaling
**Quyết định:** dùng Socket.io thay vì WebSocket thuần.
**Lý do:** đề bài yêu cầu; có sẵn room, ack callback, tự kết nối lại, heartbeat. Viết lại những thứ này trên WebSocket thuần là tốn công không cần thiết.
**Đánh đổi:** thêm một lớp giao thức; client phải dùng thư viện socket.io.

## D03. Mesh trước, SFU sau
**Lý do:** mesh đơn giản, giúp hiểu rõ SDP/ICE trước. Giới hạn của mesh (N-1 luồng upload mỗi máy) chính là lý do để làm SFU, và là câu chuyện tốt cho báo cáo.
**Hệ quả:** `max_participants_per_room` mặc định 4 cho tới khi có SFU.

## D04. Phân tầng
`api/` và `realtime/` → `services/` → `models/` + `db/`.
**Lý do:** "kick user" qua HTTP (admin) và qua socket (host) là cùng một nghiệp vụ; một hàm chung, test không cần dựng HTTP hay socket.
**Quy tắc:** handler chỉ validate đầu vào và gọi service; service không biết HTTP/socket; `schemas/` tách khỏi `models/` để không lộ `password_hash`.

## D05. Trạng thái phòng trong RAM
**Lựa chọn đã cân nhắc:** RAM vs Redis.
**Quyết định:** RAM, sau giao diện `RoomStateStore`.
**Lý do:** đơn giản, nhanh, đủ cho một instance; không thêm dịch vụ phải vận hành.
**Hệ quả:**
- Bắt buộc `--workers 1` và một container `app`.
- Restart app làm mọi người rớt khỏi phòng và phải join lại (phòng trong DB vẫn `active`).
- Khi cần mở rộng, thay cài đặt bằng Redis (cần thêm Socket.io `AsyncRedisManager`) mà không sửa handler.

## D06. Quy ước dữ liệu
- Khóa chính UUID (không đoán được, an toàn khi lộ trong URL); ngoại lệ `bigint` cho `audit_logs`, `messages` (cần thứ tự/phân trang theo con trỏ).
- `timestamptz` UTC.
- `varchar + CHECK` thay PostgreSQL ENUM vì thêm giá trị vào ENUM khó migrate.
- Email unique theo `lower(email)`.

## D07. Migration
Tạo dần theo từng tính năng, Alembic template async, naming convention đặt từ đầu, service `migrate` tách khỏi `app`, CI chạy `alembic check`, ưu tiên migration tương thích ngược. Chi tiết `01-database.md` mục 6 và `05-deployment.md` mục 7.

## D08. Token
**Quyết định:** access token JWT 15 phút (không trạng thái) + refresh token ngẫu nhiên 7 ngày (có trạng thái, lưu hash SHA-256), xoay vòng và phát hiện dùng lại theo `family_id`.
**Lý do:** access token ngắn hạn hạn chế thiệt hại khi lộ; refresh token lưu DB nên thu hồi được (đăng xuất, khóa tài khoản).
**Tinh chỉnh so với bàn bạc ban đầu:** khi phát hiện dùng lại, thu hồi **cả family (một phiên đăng nhập)** thay vì mọi phiên của user, để người dùng không bị đăng xuất khỏi thiết bị khác một cách oan. Có thể siết lại nếu muốn nghiêm hơn.
**Hệ quả:** thêm cửa sổ khoan dung 10 giây cho hai tab refresh cùng lúc.

## D09. Refresh token qua body JSON (v1)
| | Body JSON | Cookie httpOnly |
|---|---|---|
| Ưu | Dễ viết client, dễ test | JS không đọc được → chống XSS đánh cắp |
| Nhược | JS đọc được, rủi ro XSS | Phải xử lý CORS, `SameSite`, CSRF |

**Quyết định:** body ở v1; chuyển sang cookie nếu còn thời gian (ghi vào báo cáo như một cải tiến bảo mật). Riêng **trang admin web** dùng cookie (D17).

## D10. Khách (guest)
JWT riêng (`sub = guest:<uuid>`, `role = guest`), không có dòng DB, không refresh token, hết hạn theo `guest_ttl_minutes`.
**Lý do:** demo không cần đăng ký, nhưng vẫn kiểm soát được ai xin TURN credential và ai vào phòng.
**Hạn chế:** khách không tạo phòng, không vào admin; không thu hồi được token khách riêng lẻ (chỉ chờ hết hạn hoặc tắt `allow_guest` để chặn kết nối mới).

## D11. Argon2id
Dùng `pwdlib` với argon2id. Chạy hash trong thread pool để không chặn event loop. Giới hạn độ dài mật khẩu tối đa 128 để chống DoS bằng chuỗi dài. Khi email không tồn tại vẫn verify một hash giả để cân bằng thời gian phản hồi.

## D12. Role và trạng thái đọc từ DB
**Lý do:** claim `role` trong JWT có thể đã cũ (admin vừa đổi quyền/khóa). Đọc user theo PK ở mỗi request chỉ tốn một truy vấn rất nhẹ.
**Hệ quả:** khóa tài khoản và hạ quyền có hiệu lực **ngay** với HTTP; với socket thì xử lý chủ động (D15).

## D13. Hai loại cấu hình
Bí mật/hạ tầng → biến môi trường, không bao giờ lên trang admin. Vận hành → bảng `settings` + cache, sửa từ admin. `SettingsSchema` (Pydantic) là nguồn sự thật duy nhất. Chi tiết `04-settings.md`.

## D14. TURN credential tạm thời
`username = "<expiry>:<user_id>"`, `credential = base64(HMAC-SHA1(TURN_SECRET, username))`; coturn chạy `use-auth-secret`.
**Lý do:** TURN tốn băng thông VPS; không cấp credential tĩnh. Credential hết hạn tự nhiên, không cần đồng bộ DB giữa app và coturn.
**Hệ quả:** thu hồi tức thì không làm được (credential còn dùng được tới hết hạn); giảm rủi ro bằng TTL ngắn và quota của coturn.

## D15. Xác thực socket chỉ lúc kết nối
**Lý do:** kiểm tra token mỗi sự kiện tốn kém và token hết hạn giữa cuộc họp sẽ làm gián đoạn.
**Giảm thiểu rủi ro:** khi khóa tài khoản / thu hồi phiên, server chủ động gửi `force_disconnect` và ngắt socket. Kết nối lại luôn phải xác thực lại.
**Rủi ro còn lại:** socket của một token đã bị thu hồi *mà server không biết* vẫn sống tới khi ngắt. Chấp nhận vì mọi đường thu hồi đều đi qua service có ngắt socket.

## D16. Quy tắc offer và đàm phán lại
Người mới gửi `offer` cho từng người cũ (tránh glare lúc vào phòng). Với đàm phán lại (share màn hình...), dùng mẫu "perfect negotiation" với `polite` xác định bằng so sánh `peer_id`. Chi tiết `03-socket-events.md` mục 7.

## D17. Admin web bằng Jinja2 + HTMX
**Lý do:** không cần build frontend, vẫn là Python; chỉ cần 4 trang. API JSON `/admin/api/...` làm trước và test đầy đủ, trang web là lớp mỏng phía trên.
**Xác thực:** cookie `httpOnly`, `Secure`, `SameSite=Strict`, `Path=/admin` + CSRF token. Xem Q2.
**Phương án đã cân nhắc:** SQLAdmin (nhanh nhưng kém linh hoạt cho trang phòng live và cấu hình).

## D18. Caddy thay vì Nginx
HTTPS tự động (Let's Encrypt), cấu hình ngắn, WebSocket không cần cấu hình thêm. Đánh đổi: ít phổ biến hơn Nginx trong công việc thực tế; nếu muốn học Nginx thì đổi được mà không ảnh hưởng thiết kế khác.

## D19. coturn dùng `network_mode: host`
Tránh phải map dải UDP lớn qua Docker bridge và để coturn thấy địa chỉ nguồn đúng. Đánh đổi: mất cô lập mạng của container này, và dev trên Windows/macOS phải làm khác (`05-deployment.md` mục 4.4).

## D20. Rate limit trong bộ nhớ
slowapi ở v1. Đánh đổi: bộ đếm mất khi restart và không dùng chung giữa nhiều instance. Khi chuyển Redis (D05) thì chuyển luôn rate limit.

## D21. Client JS thuần
Không React/Vue để tập trung vào backend/devops. Client gồm 3 trang HTML + vài module JS. Nếu cần giao diện đẹp để demo, làm ở cuối, không ảnh hưởng thiết kế backend.

## D22. Mục tiêu độ trễ
"Độ trễ bằng 0" không thể đạt (giới hạn vật lý + mã hóa + mạng). Mục tiêu thực tế **< 200 ms một chiều**, đo bằng `getStats()` và đối chiếu thủ công; ghi số liệu thật vào báo cáo.

## D23. Tài liệu trước, code sau
Bạn chọn thiết kế xong rồi mới code. Hai lưu ý đã thống nhất: ERD vẽ đủ nhưng migration vẫn tạo dần; tài liệu là bản sống, thấy sai khi code thì sửa docs luôn.

---

## Câu hỏi còn mở

Những mục đánh dấu **[CẦN CHỐT]** cần bạn quyết định trước khi code; các mục còn lại có thể chốt khi tới bước tương ứng.

| # | Câu hỏi | Mình đề xuất | Cần chốt trước |
|---|---|---|---|
| Q1 | **[CẦN CHỐT]** Hệ điều hành dev của bạn (Linux / macOS / Windows) và đã cài Docker chưa? | Ảnh hưởng cách chạy coturn ở dev (`05` mục 4.4) | A1 |
Hệ điều hành windows
| Q2 | Phiên đăng nhập của trang admin web: giữ cả access và refresh token trong cookie và middleware tự refresh, hay cookie phiên riêng thời hạn dài hơn? | Cookie httpOnly chứa token, middleware tự refresh | A6 |
middleware tự refresh
| Q3 | **[CẦN CHỐT]** Khi bị kick, người dùng bị cấm vào lại **tới khi phòng đóng**. Bạn có muốn host "bỏ cấm" được không? | Chưa cần ở v1 | A4 |
chưa cần thiết
| Q4 | aiortc có giới hạn được dải cổng UDP không, và chịu được bao nhiêu subscriber? | Thử nghiệm sớm ở đầu A10, ghi kết quả vào báo cáo | A10 |
ở mức mà cho webapp chạy tốt nhất không gây lag
| Q5 | **[CẦN CHỐT]** Phòng có cho khách xem lịch sử chat không? Hiện tại: ai đang trong phòng hoặc host đều xem được | Giữ như hiện tại | A8 |
cho xem lịch sử chat, kể cả người mới vào
| Q6 | Bật TURNS (TURN qua TLS, cổng 5349 hoặc 443) cho mạng chặn UDP/cổng lạ? Cần chia sẻ chứng chỉ Caddy | Làm ở B3 nếu còn thời gian | B3 |
tui chưa tìm hiểu cài này
| Q7 | **[CẦN CHỐT]** Phòng đã đóng: `GET /rooms/{code}` trả 404 hay 200 với `status: closed`? | 404 (không lộ thông tin) | A4 |
200
| Q8 | Giữ chỗ khi rớt mạng (grace period): người rớt mạng 10 giây có được tự quay lại vị trí cũ không? | Ngoài phạm vi v1, ghi vào cải tiến | Sau A9 |
có được quay lại ở v1
| Q9 | Ghi hình phòng (aiortc `MediaRecorder`): có làm không, lưu ở đâu, quyền xem? | Ngoài phạm vi trừ khi còn thời gian | Sau A10 |
v2 sẽ làm
| Q10 | **[CẦN CHỐT]** Làm một mình hay theo nhóm, bao nhiêu tuần? | Để chia lại mốc thời gian cho lộ trình ở README | Trước khi code |
làm một mình, thời gian có thể  chia làm 2 giai đoạn
giai đoạn1: xây dựng dự án ở bản v1
giai đoạn 2: deploy
giai đoạn: phát triển và kiểm thử
giai đoạn 4: hoàn thiện

## Cải tiến để dành (không làm ở v1)

- OAuth Google/GitHub, quên mật khẩu qua email, 2FA
- Refresh token qua cookie cho toàn bộ client
- Redis cho trạng thái phòng, rate limit, nhiều instance
- Giữ chỗ khi rớt mạng; bỏ cấm người bị kick
- Simulcast / SVC (cần SFU mạnh hơn aiortc, ví dụ mediasoup hoặc LiveKit)
- Ghi hình phòng; phụ đề / chuyển giọng nói thành văn bản
- Loki cho log tập trung; tracing (OpenTelemetry)
