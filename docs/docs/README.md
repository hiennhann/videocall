# Video Call / Livestream: Tài liệu thiết kế

> **Trạng thái:** bản nháp v0.1, chờ review. Chưa có dòng code nào.
> **Công nghệ chính:** Python (FastAPI, python-socketio, aiortc), PostgreSQL, coturn, Docker, Caddy.
> **Định hướng:** backend + devops. Client chỉ là JS thuần tối giản để kiểm tra backend.

## 1. Mục lục

| File | Nội dung | Đọc khi nào |
|---|---|---|
| [`01-database.md`](01-database.md) | ERD, chi tiết từng bảng, index, ràng buộc, kế hoạch migration | Trước khi viết model |
| [`02-api.md`](02-api.md) | Toàn bộ endpoint HTTP, request/response mẫu, mã lỗi, rate limit | Trước khi viết `api/` |
| [`03-socket-events.md`](03-socket-events.md) | Sự kiện Socket.io, luồng signaling, phân quyền host, xử lý lỗi | Trước khi viết `realtime/` (**cốt lõi**) |
| [`04-settings.md`](04-settings.md) | Cấu hình vận hành sửa được từ trang admin | Trước khi viết `settings_service` |
| [`05-deployment.md`](05-deployment.md) | Docker, mạng, cổng, coturn, Caddy, CI/CD, giám sát, load test | Trước khi vào giai đoạn B |
| [`06-decisions.md`](06-decisions.md) | Các quyết định kiến trúc và lý do, câu hỏi còn mở | Khi viết báo cáo |

## 2. Phạm vi

### 2.1 MVP (bắt buộc)
- Đăng ký / đăng nhập / khách (guest), JWT + refresh token xoay vòng
- Tạo phòng, vào phòng bằng mã (có thể đặt mật khẩu phòng)
- Gọi video 1-1 và nhóm nhỏ (mesh, tối đa 4 người)
- Bật/tắt mic, camera; chia sẻ màn hình; chat realtime
- TURN credential tạm thời, chỉ cấp cho người đã xác thực
- Trang admin: quản lý tài khoản, phòng, cấu hình, audit log

### 2.2 Mở rộng (nếu còn thời gian)
- SFU bằng aiortc cho nhóm đông và livestream 1-nhiều (`mode = livestream`)
- Chỉ số mạng realtime trên giao diện (RTT, packet loss, bitrate)
- Giơ tay, kick/mute bởi host, ghi hình phòng
- Chuyển trạng thái phòng sang Redis, chạy nhiều instance

### 2.3 Ngoài phạm vi
Đăng nhập OAuth, quên mật khẩu qua email, 2FA, app mobile native, simulcast/SVC.

## 3. Mục tiêu phi chức năng

| Mục tiêu | Chỉ tiêu | Cách đo |
|---|---|---|
| Độ trễ media | **< 200 ms** một chiều (không thể đạt "0") | `getStats()`: `currentRoundTripTime / 2`, kết hợp đo thủ công |
| Mất gói | < 2% trong điều kiện mạng bình thường | `getStats()`: `packetsLost` |
| Kết nối khác mạng | Thành công kể cả khi NAT đối xứng (qua TURN) | Test 4G ↔ Wi-Fi |
| Bảo mật | Không lưu mật khẩu thô; token thu hồi được; secret không nằm trong git | Review + test |
| Vận hành | Deploy bằng 1 lệnh, rollback được, có giám sát và backup | CI/CD, Grafana |
| Chất lượng code | Test tự động cho service, API, socket; CI xanh mới merge | GitHub Actions |

## 4. Kiến trúc tổng quan

```
                         Internet
                            │
        ┌───────────────────┼─────────────────────┐
        │ 443/tcp           │ 3478/udp+tcp        │ 49152-49252/udp
        ▼                   ▼  (STUN/TURN)        ▼  (TURN relay)
   ┌─────────┐         ┌─────────┐
   │  Caddy  │         │ coturn  │
   │ (HTTPS) │         └─────────┘
   └────┬────┘
        │ HTTP + WebSocket
        ▼
   ┌──────────────────────────────┐        ┌────────────┐
   │ app (FastAPI + Socket.io)    │───────▶│ PostgreSQL │
   │  api/ ─┐                     │        └────────────┘
   │        ├─▶ services/ ─▶ db   │
   │ realtime/┘   │               │        ┌────────────┐
   │              └─▶ state (RAM) │        │ Prometheus │◀── /metrics
   └──────────────────────────────┘        │  + Grafana │
                                           └────────────┘

   Trình duyệt A ◀══════ media (SRTP, P2P hoặc qua TURN) ══════▶ Trình duyệt B
```

Server **chỉ trung chuyển tín hiệu (signaling)**. Media đi thẳng giữa các trình duyệt, hoặc qua TURN khi P2P không thông, hoặc qua SFU ở giai đoạn sau.

## 5. Công nghệ

| Phần | Lựa chọn |
|---|---|
| Web framework | FastAPI (async), Uvicorn |
| Realtime | python-socketio (AsyncServer, mount vào ASGI) |
| Media server (giai đoạn sau) | aiortc |
| ORM / migration | SQLAlchemy 2.0 async + Alembic (template async) |
| Database | PostgreSQL 16 |
| Mật khẩu / JWT | argon2 (`pwdlib`) / PyJWT |
| Rate limit | slowapi (bộ nhớ) → Redis nếu cần |
| Admin web | Jinja2 + HTMX |
| Client | HTML + JS thuần (WebRTC API) |
| Reverse proxy | Caddy (HTTPS tự động) |
| STUN/TURN | coturn |
| Giám sát | Prometheus + Grafana, log JSON |
| CI/CD | GitHub Actions, GHCR, deploy qua SSH |
| Test | pytest, pytest-asyncio, httpx, python-socketio client |

Ghi chú: **WebRTC trong trình duyệt bắt buộc dùng JavaScript** (camera, mic, `RTCPeerConnection`). Python đảm nhiệm toàn bộ backend, signaling và (sau này) SFU.

## 6. Lộ trình

### Giai đoạn A: Xây dựng

| Bước | Nội dung | Migration | Tài liệu |
|---|---|---|---|
| A1 | Khung dự án: FastAPI + Postgres + Compose, `/health`, `/ready`, Alembic | baseline | 05, 06 |
| A2 | Auth: register, login, refresh, logout, guest, `/me` | `0001 users`, `0002 refresh_tokens` | 01, 02 |
| A3 | Admin API: user, settings, audit log; **CLI `create-admin`** | `0003 users_admin_cols`, `0004 settings`, `0005 audit_logs` | 02, 04 |
| A4 | Rooms + signaling có xác thực, áp dụng settings, kick, đóng phòng | `0006 rooms` | 02, 03 |
| A5 | Client tối giản: login, lobby, gọi 1-1 | | 03 |
| A6 | Trang admin (Jinja2 + HTMX) | | 02 |
| A7 | coturn + `/turn-credentials` | | 02, 05 |
| A8 | Chat (lưu lịch sử), chia sẻ màn hình, mute/camera | `0007 messages` | 03 |
| A9 | Mesh nhiều người | | 03 |
| A10 | SFU + livestream | (có thể thêm cột/bảng) | 03 |
| A11 | Metrics (`/metrics`), log có cấu trúc | | 05 |

> **Điều chỉnh so với các trao đổi trước:** lệnh CLI `create-admin` chuyển từ A2 sang A3, vì cột `role` chỉ được thêm ở migration `0003`.

### Giai đoạn B: Deploy / DevOps

| Bước | Nội dung |
|---|---|
| B1 | VPS, domain, firewall |
| B2 | Caddy + HTTPS, WebSocket qua proxy, khóa `/admin` |
| B3 | coturn production (secret, giới hạn cổng, chặn dải IP nội bộ) |
| B4 | CI/CD GitHub Actions: test → build → push → deploy → rollback |
| B5 | Prometheus + Grafana + cảnh báo |
| B6 | Load test bằng bot aiortc, đo giới hạn |
| B7 | Báo cáo: sơ đồ, số liệu, bài học |

## 7. Quy ước chung của dự án

- **Ngôn ngữ:** code, tên biến, tên bảng bằng tiếng Anh; tài liệu và comment giải thích bằng tiếng Việt.
- **Phân tầng:** `api/` và `realtime/` → `services/` → `models/` + `db/`. Handler không chứa logic nghiệp vụ.
- **Định danh:** UUID; thời gian `timestamptz` (UTC); JSON dùng `snake_case`.
- **Git:** nhánh `main` luôn chạy được; làm theo nhánh `feat/...`; commit theo dạng `feat:`, `fix:`, `docs:`, `chore:`.
- **Tài liệu là bản sống:** sửa code mà đổi thiết kế thì sửa docs trong cùng commit.
- **Bí mật** chỉ nằm trong biến môi trường (`.env` không commit; `.env.example` thì commit).

## 8. Thuật ngữ

| Từ | Nghĩa |
|---|---|
| **WebRTC** | Bộ API của trình duyệt để truyền audio/video/dữ liệu realtime |
| **Signaling** | Việc trao đổi thông tin kết nối (SDP, ICE) giữa hai bên trước khi có media; WebRTC không quy định cách làm, ta dùng Socket.io |
| **SDP** | Văn bản mô tả phiên media (codec, địa chỉ, khóa mã hóa); có 2 loại: offer và answer |
| **ICE candidate** | Một địa chỉ (IP:port) có thể dùng để kết nối |
| **STUN** | Máy chủ giúp client biết IP:port công khai của mình |
| **TURN** | Máy chủ chuyển tiếp media khi hai bên không kết nối trực tiếp được (NAT đối xứng, tường lửa) |
| **Mesh** | Mỗi người nối trực tiếp với mọi người khác; N người thì mỗi máy upload N-1 luồng |
| **SFU** | Server nhận 1 luồng từ mỗi người rồi chuyển tiếp cho người khác, không giải mã |
| **Host / owner** | Chủ phòng: người tạo phòng, có quyền kick, mute, đóng phòng |

## 9. Checklist review dành cho bạn

Đọc theo thứ tự `06 → 02 → 03 → 01 → 04 → 05` và đánh dấu:

- [ ] Phạm vi MVP và mở rộng ở mục 2 đã đúng ý?
- [ ] Các quyết định ở `06-decisions.md` mục "Câu hỏi còn mở" cần bạn chốt (có đánh dấu **[CẦN CHỐT]**)
- [ ] Danh sách endpoint (`02`) có thiếu hoặc thừa không?
- [ ] Danh sách sự kiện socket (`03`) và quyền host có hợp lý không?
- [ ] Các bảng và cột (`01`) có thiếu trường nào bạn cần không?
- [ ] Danh sách cấu hình (`04`) có muốn thêm/bớt cấu hình nào không?
- [ ] Sơ đồ cổng và container (`05`) có khớp với VPS bạn định thuê không?
