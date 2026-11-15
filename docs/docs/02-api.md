# 02. API (HTTP)

> Base URL: `/api/v1`. Riêng `/health`, `/ready`, `/metrics` nằm ngoài prefix.
> Phần realtime (Socket.io) xem `03-socket-events.md`.

## 0. Quy ước chung

| Hạng mục | Quy ước |
|---|---|
| Định dạng | JSON, UTF-8, `snake_case` |
| Thời gian | ISO 8601 UTC: `2026-11-15T08:30:00Z` |
| ID | UUID (riêng phòng dùng `code`) |
| Xác thực | Header `Authorization: Bearer <access_token>` |
| Phân trang | `?page=1&page_size=20` (`page_size` tối đa 100) → `{ "items": [], "total": 0, "page": 1, "page_size": 20 }` |
| Request ID | Server sinh `X-Request-ID` cho mọi response, ghi vào log |
| CORS | Chỉ cho phép origin trong biến môi trường `ALLOWED_ORIGINS` |

### Định dạng lỗi thống nhất

```json
{
  "error": {
    "code": "EMAIL_TAKEN",
    "message": "Email đã được sử dụng.",
    "details": {}
  }
}
```

Lỗi validate (422) có `details.fields`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Dữ liệu không hợp lệ.",
    "details": { "fields": { "password": "Tối thiểu 8 ký tự." } }
  }
}
```

`code` là chuỗi ổn định để client xử lý; `message` chỉ để hiển thị.

### Quy tắc dữ liệu đầu vào

| Trường | Quy tắc |
|---|---|
| `email` | Hợp lệ theo `email-validator`, tối đa 254 ký tự, chuyển lowercase, trim |
| `password` | **8-128 ký tự** (tối thiểu chỉnh được bằng `password_min_length`), không ép ký tự đặc biệt. Giới hạn 128 để chống gửi chuỗi khổng lồ làm nặng argon2 |
| `display_name` | Trim, 2-50 ký tự, loại bỏ ký tự điều khiển |
| `room.name` | 0-100 ký tự |
| `room.password` | 4-64 ký tự |

## 1. Xác thực và token

### 1.1 Access token (JWT, HS256)

```json
{
  "iss": "videocall",
  "typ": "access",
  "sub": "3f0c...-uuid",
  "role": "user",
  "name": "An",
  "iat": 1763195400,
  "exp": 1763196300,
  "jti": "uuid",
  "family_id": "uuid"
}
```

- Thời hạn mặc định **15 phút** (`access_token_ttl_minutes`).
- Khóa ký `JWT_SECRET` (≥ 32 byte ngẫu nhiên) nằm trong biến môi trường.
- Claim `role` chỉ để client hiển thị giao diện. **Server luôn đọc user từ DB** ở mỗi request (tìm theo PK, rất nhẹ) để kiểm tra `is_active` và `role`. Nhờ vậy khóa tài khoản hoặc đổi quyền có tác dụng ngay, không phải chờ token hết hạn.
- `family_id` có trong token của tài khoản và định danh phiên đăng nhập. Endpoint đổi mật khẩu dùng claim đã ký này để giữ refresh token của phiên hiện tại.
- Khách (guest): `sub = "guest:<uuid>"`, `role = "guest"`, không có dòng trong DB nên không kiểm tra DB; hết hạn theo `guest_ttl_minutes`.

Từ A3, server đọc `role`, `is_active` và `must_change_password` từ DB khi xác thực tài khoản. Migration `0003` đặt giá trị mặc định cho các tài khoản A2. A4 tích hợp ngắt socket khi thu hồi phiên.

### 1.2 Refresh token

- Chuỗi ngẫu nhiên 32 byte (`secrets.token_urlsafe`), **không phải JWT**.
- DB chỉ lưu SHA-256 của nó (`refresh_tokens.token_hash`).
- Thời hạn mặc định 7 ngày (`refresh_token_ttl_days`).
- v1 gửi/nhận qua **body JSON** (xem `06-decisions.md` D09).

### 1.3 Xoay vòng và phát hiện dùng lại

Mỗi lần `/auth/refresh`:
1. Tìm token theo hash. Không thấy hoặc hết hạn → 401 `INVALID_REFRESH_TOKEN`.
2. Token chưa bị thu hồi → thu hồi nó (`revoked_at = now()`), tạo token mới cùng `family_id`, ghi `replaced_by_id`, trả cặp mới.
3. Token **đã bị thu hồi** (bị dùng lại):
   - Nếu mới xoay vòng trong **10 giây**: coi là hai tab refresh cùng lúc → trả 401 nhưng **không** thu hồi family; client thử lại với token mới nhất trong storage.
   - Ngoài 10 giây: coi là token bị lộ → **thu hồi cả family** và trả 401. Ghi log mức `warning`.

### 1.4 Tài khoản bị buộc đổi mật khẩu

Khi `must_change_password = true`, đăng nhập vẫn thành công nhưng mọi endpoint **trừ** `GET /me`, `POST /me/password`, `POST /auth/logout`, `GET /config/public` trả 403 `PASSWORD_CHANGE_REQUIRED`.

### 1.5 Xác thực cho trang admin web

Trang admin (Jinja2 + HTMX) dùng cookie `httpOnly`, `Secure`, `SameSite=Strict`, `Path=/admin`, kèm CSRF token cho các request thay đổi dữ liệu. Chi tiết chốt ở bước A6 (xem `06-decisions.md`, câu hỏi mở Q2). API JSON `/api/v1/admin/*` chỉ chấp nhận Bearer token.

## 2. Rate limit

Triển khai bằng slowapi (bộ nhớ) ở v1; chuyển Redis nếu chạy nhiều instance. Vượt giới hạn → 429 + header `Retry-After`.

| Endpoint | Giới hạn | Khóa đếm |
|---|---|---|
| `POST /auth/register` | 5 / giờ | IP |
| `POST /auth/login` | 20 / phút | IP |
| `POST /auth/login` (sai mật khẩu) | `login_max_attempts` lần, khóa `login_lockout_minutes` phút | email + IP |
| `POST /auth/refresh` | 30 / phút | IP |
| `POST /auth/guest` | 10 / phút | IP |
| `POST /rooms` | 10 / phút | user |
| `GET /rooms/{code}` | 30 / phút | IP (chống dò mã phòng) |
| `GET /turn-credentials` | 10 / phút | user |
| `/admin/*` | 120 / phút | user |

Khi chạy sau Caddy, lấy IP thật từ `X-Forwarded-For` và **chỉ tin header này khi request đến từ proxy đã biết** (cấu hình `--forwarded-allow-ips`). Nếu không, kẻ tấn công tự đặt header để né rate limit.

## 3. Hệ thống

| Method | Path | Auth | Mô tả |
|---|---|---|---|
| GET | `/health` | Không | Liveness: process còn sống. Không đụng DB. `200 {"status":"ok"}` |
| GET | `/ready` | Không | Readiness: kiểm tra kết nối DB (`SELECT 1`) và migration đã ở `head`. `200` hoặc `503`. Dùng cho Docker healthcheck |
| GET | `/metrics` | Mạng nội bộ | Prometheus. Caddy chặn từ bên ngoài |
| GET | `/api/v1/config/public` | Không | Cấu hình công khai cho client |

`GET /api/v1/config/public`:

```json
{
  "allow_registration": true,
  "allow_guest": true,
  "maintenance_mode": false,
  "maintenance_message": "",
  "password_min_length": 8,
  "allow_screen_share": true,
  "chat_enabled": true
}
```

## 4. Auth

### POST `/auth/register`

Request:
```json
{ "email": "an@example.com", "password": "matkhau-dai-123", "display_name": "An" }
```
Response `201`:
```json
{
  "id": "uuid",
  "email": "an@example.com",
  "display_name": "An",
  "role": "user",
  "created_at": "2026-11-15T08:30:00Z"
}
```
Không tự đăng nhập; client gọi `/auth/login` sau.

| Lỗi | Code | Khi |
|---|---|---|
| 403 | `REGISTRATION_DISABLED` | `allow_registration = false` |
| 409 | `EMAIL_TAKEN` | Email đã tồn tại |
| 422 | `VALIDATION_ERROR` | Sai định dạng |
| 429 | `RATE_LIMITED` | |

Lưu ý: endpoint này **có** lộ việc email đã tồn tại (409). Đây là đánh đổi chấp nhận được ở v1 để người dùng biết mình đã có tài khoản; được rate limit để hạn chế dò email.

### POST `/auth/login`

Request: `{ "email": "...", "password": "..." }`

Response `200`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "Zk3...",
  "token_type": "bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "an@example.com",
    "display_name": "An",
    "role": "user",
    "must_change_password": false
  }
}
```

| Lỗi | Code | Khi |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Sai email **hoặc** sai mật khẩu (cùng một lỗi, không lộ email nào tồn tại) |
| 403 | `ACCOUNT_DISABLED` | Đúng mật khẩu nhưng tài khoản bị khóa |
| 429 | `RATE_LIMITED` / `LOGIN_LOCKED` | Quá số lần thử |

Chống dò email qua thời gian phản hồi: khi email không tồn tại, vẫn chạy một lần verify hash giả để thời gian gần bằng nhau.

Từ A3, đăng nhập thành công cập nhật `last_login_at`.

### POST `/auth/refresh`

Request: `{ "refresh_token": "Zk3..." }` → Response giống `/auth/login` (không có `user`).
Lỗi: 401 `INVALID_REFRESH_TOKEN`, 403 `ACCOUNT_DISABLED` hoặc `PASSWORD_CHANGE_REQUIRED`.

### POST `/auth/logout`

Request: `{ "refresh_token": "..." }` → `204`. Thu hồi token đó (cả family). Luôn trả 204 kể cả token không tồn tại (idempotent).

### POST `/auth/logout-all`

Cần Bearer. Thu hồi mọi refresh token của user, ngắt các socket đang kết nối → `204`.

### POST `/auth/guest`

Request: `{ "display_name": "Khách 1" }`
Response `200`:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": { "id": "guest:uuid", "display_name": "Khách 1", "role": "guest" }
}
```
Không có refresh token. Hết hạn thì nhập tên lại. Lỗi: 403 `GUEST_DISABLED`, 503 `MAINTENANCE_MODE`.

Khách **không** được: tạo phòng, gọi admin API, đổi tên/mật khẩu. Khách được: vào phòng, chat, xin TURN credential (nếu `turn_allow_guests`).

## 5. Người dùng hiện tại

### GET `/me`
```json
{
  "id": "uuid",
  "email": "an@example.com",
  "display_name": "An",
  "role": "user",
  "is_guest": false,
  "must_change_password": false,
  "created_at": "2026-11-15T08:30:00Z"
}
```
Với khách: `email = null`, `is_guest = true`, thêm `expires_at`.

### PATCH `/me`
`{ "display_name": "An Nguyen" }` → trả user. Khách: 403 `GUEST_NOT_ALLOWED`.

### POST `/me/password`
`{ "current_password": "...", "new_password": "..." }` → `204`.
- Sai mật khẩu hiện tại: 400 `WRONG_PASSWORD`.
- Mật khẩu mới trùng cũ: 400 `PASSWORD_UNCHANGED`.
- Thành công: **thu hồi refresh token của các phiên khác**, giữ phiên theo `family_id` trong access token và trả `204`. Từ A3, đặt `must_change_password = false`. Từ A4, ngắt socket của các phiên khác.

## 6. Phòng

Mật khẩu phòng được kiểm tra ở sự kiện socket `join_room`, **không** có endpoint HTTP riêng, để chỉ một chỗ quyết định ai được vào.

### POST `/rooms`

Khách không được gọi (403 `GUEST_NOT_ALLOWED`).

Request:
```json
{
  "name": "Họp nhóm",
  "mode": "meeting",
  "is_private": true,
  "password": "1234",
  "max_participants": 4
}
```
Tất cả trường đều tùy chọn (`mode` mặc định `meeting`, `max_participants` mặc định theo settings). `is_private = true` bắt buộc có `password`.

Response `201`:
```json
{
  "code": "abc-defg-hij",
  "name": "Họp nhóm",
  "mode": "meeting",
  "is_private": true,
  "max_participants": 4,
  "host_id": "uuid",
  "status": "active",
  "created_at": "2026-11-15T08:30:00Z"
}
```

| Lỗi | Code | Khi |
|---|---|---|
| 400 | `MODE_NOT_SUPPORTED` | `mode = livestream` khi SFU chưa bật |
| 409 | `ROOM_LIMIT_REACHED` | Đủ `max_rooms_per_user` phòng đang mở |
| 422 | `VALIDATION_ERROR` | `max_participants` vượt `max_participants_per_room`, thiếu password... |
| 503 | `MAINTENANCE_MODE` | Đang bảo trì |

### GET `/rooms/{code}`

Công khai với người đã xác thực; dùng ở lobby để biết có cần nhập mật khẩu không.
```json
{
  "code": "abc-defg-hij",
  "name": "Họp nhóm",
  "mode": "meeting",
  "has_password": true,
  "participants": 2,
  "max_participants": 4,
  "status": "active"
}
```
404 `ROOM_NOT_FOUND`. Phòng `closed` trả 200 với `status: "closed"` hoặc 404 (chốt khi code; ưu tiên 404 để không lộ).

### GET `/rooms/mine`
Danh sách phòng `active` do user làm host. (Khai báo route này **trước** `/rooms/{code}` để không bị bắt nhầm là code.)

### DELETE `/rooms/{code}`
Chỉ host. Đóng phòng (`closed_reason = host`), đẩy sự kiện `room_closed` cho mọi người → `204`. 403 `NOT_ROOM_HOST`, 404.

### GET `/rooms/{code}/messages?before=<id>&limit=50`
Lịch sử chat, mới nhất trước, phân trang theo con trỏ (`limit` tối đa 100).
```json
{
  "items": [
    { "id": 1201, "sender_name": "An", "user_id": "uuid", "content": "Chào mọi người", "created_at": "..." }
  ],
  "next_before": 1180
}
```
Quyền: người **đang ở trong phòng** hoặc host. Khác → 403 `NOT_IN_ROOM`. Trả rỗng nếu `chat_history_enabled = false`.

## 7. TURN

### GET `/turn-credentials`

Cần Bearer (user hoặc khách nếu `turn_allow_guests`).

Response:
```json
{
  "urls": [
    "stun:turn.example.com:3478",
    "turn:turn.example.com:3478?transport=udp",
    "turn:turn.example.com:3478?transport=tcp"
  ],
  "username": "1763209800:3f0c...-uuid",
  "credential": "base64-hmac",
  "ttl": 14400
}
```

Cách sinh (khớp với `use-auth-secret` của coturn):
- `username = "<unix_expiry>:<user_id>"`, `unix_expiry = now + ttl`
- `credential = base64( HMAC-SHA1( TURN_SECRET, username ) )`

(coturn quy định dùng HMAC-SHA1; đây không phải điểm yếu vì khóa là bí mật phía server.)

Client dùng làm `iceServers` của `RTCPeerConnection` và **lấy lại trước khi hết `ttl`** nếu cuộc gọi kéo dài. Lỗi: 401, 403 `TURN_DISABLED` (khi `turn_enabled = false`, endpoint chỉ trả STUN) / `GUEST_NOT_ALLOWED`.

## 8. Admin

Mọi route `/admin/*` dùng dependency `require_admin`: đọc user từ DB, kiểm tra `role = 'admin'` và `is_active`. Không đủ quyền → 403 `FORBIDDEN`. Mọi thao tác **ghi** tạo một dòng audit log **trong cùng transaction** với thay đổi chính.

### 8.1 Dashboard

`GET /admin/dashboard`
```json
{
  "online_connections": 12,
  "active_rooms": 3,
  "active_participants": 9,
  "total_users": 148,
  "new_users_per_day": [ { "date": "2026-11-14", "count": 4 } ],
  "turn": null
}
```
`turn` (băng thông relay) chỉ có giá trị nếu cấu hình `PROMETHEUS_URL`; không thì `null` và xem ở Grafana.

A3 báo số liệu tài khoản. A4 nối số liệu phòng và kết nối Socket.IO.

### 8.2 Người dùng

| Method | Path | Mô tả |
|---|---|---|
| GET | `/admin/users?q=&role=&is_active=&page=&page_size=` | Danh sách, tìm theo email/tên |
| GET | `/admin/users/{id}` | Chi tiết + `active_sessions` (số refresh token còn hiệu lực) + `is_online` |
| PATCH | `/admin/users/{id}` | `{ "role"?, "is_active"?, "display_name"? }` |
| POST | `/admin/users/{id}/reset-password` | Sinh mật khẩu tạm |
| POST | `/admin/users/{id}/revoke-sessions` | Buộc đăng xuất |
| DELETE | `/admin/users/{id}` | Xóa tài khoản |

Phần tử danh sách:
```json
{
  "id": "uuid", "email": "an@example.com", "display_name": "An",
  "role": "user", "is_active": true,
  "last_login_at": "2026-11-15T07:00:00Z", "created_at": "2026-10-01T00:00:00Z"
}
```

Quy tắc nghiệp vụ:
- Admin **không** tự đổi `role` / `is_active` của chính mình hoặc tự xóa mình → 409 `CANNOT_MODIFY_SELF`.
- Không hạ quyền, khóa hoặc xóa **admin cuối cùng** → 409 `LAST_ADMIN`.
- **Khóa tài khoản** (`is_active: false`) phải có tác dụng ngay: thu hồi mọi refresh token, phát `force_disconnect` và ngắt socket đang kết nối, đưa user ra khỏi phòng.
- `reset-password` trả `{ "temporary_password": "..." }` **một lần duy nhất**; đặt `must_change_password = true`, thu hồi mọi phiên. Mật khẩu tạm **không** được ghi vào log hay audit.
- `DELETE` đóng các phòng đang mở của user trước (xem `01-database.md` mục 4).

### 8.3 Phòng

| Method | Path | Mô tả |
|---|---|---|
| GET | `/admin/rooms` | Phòng đang hoạt động (từ trạng thái RAM + DB), kèm danh sách người |
| DELETE | `/admin/rooms/{code}` | Đóng phòng (`closed_reason = admin`), ngắt mọi người |
| POST | `/admin/rooms/{code}/kick` | `{ "peer_id" }` hoặc `{ "user_id" }` |

```json
{
  "code": "abc-defg-hij", "name": "Họp nhóm", "mode": "meeting",
  "host": { "id": "uuid", "display_name": "An" },
  "participants": [
    { "peer_id": "sid", "user_id": "uuid", "display_name": "An", "is_guest": false, "joined_at": "..." }
  ],
  "created_at": "..."
}
```

### 8.4 Cấu hình

| Method | Path | Mô tả |
|---|---|---|
| GET | `/admin/settings` | Toàn bộ cấu hình + metadata |
| PATCH | `/admin/settings` | Cập nhật một hoặc nhiều khóa |

`GET`:
```json
{
  "allow_guest": {
    "value": true, "default": true, "is_default": true,
    "type": "bool", "category": "access",
    "description": "Cho phép đăng nhập bằng tên khách."
  },
  "max_participants_per_room": {
    "value": 4, "default": 4, "is_default": true,
    "type": "int", "min": 2, "max": 50, "category": "rooms",
    "description": "Số người tối đa trong một phòng."
  }
}
```

`PATCH` (khóa không có trong body giữ nguyên; giá trị `null` = reset về mặc định):
```json
{ "allow_guest": false, "max_participants_per_room": 6, "maintenance_message": null }
```
Validate toàn bộ trước, **sai một khóa thì không áp dụng khóa nào** (422 kèm `details.fields`). Khóa lạ → 422 `UNKNOWN_SETTING`. Chi tiết xem `04-settings.md`.

### 8.5 Audit log

`GET /admin/audit-logs?actor=&action=&target_type=&from=&to=&page=&page_size=` (mới nhất trước).
```json
{
  "id": 981, "actor_id": "uuid", "actor_label": "admin@example.com",
  "action": "user.lock", "target_type": "user", "target_id": "uuid",
  "detail": { "before": { "is_active": true }, "after": { "is_active": false } },
  "ip": "203.0.113.7", "created_at": "2026-11-15T08:30:00Z"
}
```

Danh sách `action` chuẩn:

| action | Khi nào |
|---|---|
| `admin.login` | Admin đăng nhập vào trang admin |
| `user.update` | Đổi tên/role |
| `user.lock` / `user.unlock` | Khóa / mở khóa |
| `user.reset_password` | Reset mật khẩu (detail không chứa mật khẩu) |
| `user.revoke_sessions` | Buộc đăng xuất |
| `user.delete` | Xóa tài khoản |
| `room.close` | Admin đóng phòng |
| `room.kick` | Admin kick người |
| `settings.update` | Đổi cấu hình (detail: các khóa, giá trị trước/sau) |

## 9. Bảng mã lỗi

| HTTP | Code | Ý nghĩa |
|---|---|---|
| 400 | `WRONG_PASSWORD`, `PASSWORD_UNCHANGED`, `MODE_NOT_SUPPORTED` | Yêu cầu sai logic |
| 401 | `UNAUTHENTICATED` | Thiếu token |
| 401 | `TOKEN_EXPIRED`, `TOKEN_INVALID` | Token hết hạn / sai (client nên thử refresh) |
| 401 | `INVALID_CREDENTIALS`, `INVALID_REFRESH_TOKEN` | |
| 403 | `FORBIDDEN` | Không đủ quyền |
| 403 | `ACCOUNT_DISABLED` | Tài khoản bị khóa |
| 403 | `REGISTRATION_DISABLED`, `GUEST_DISABLED`, `TURN_DISABLED` | Tính năng bị admin tắt |
| 403 | `GUEST_NOT_ALLOWED` | Khách không được làm việc này |
| 403 | `PASSWORD_CHANGE_REQUIRED` | Phải đổi mật khẩu trước |
| 403 | `NOT_ROOM_HOST`, `NOT_IN_ROOM` | |
| 404 | `NOT_FOUND`, `ROOM_NOT_FOUND`, `USER_NOT_FOUND` | |
| 409 | `EMAIL_TAKEN`, `ROOM_LIMIT_REACHED`, `LAST_ADMIN`, `CANNOT_MODIFY_SELF` | Xung đột |
| 422 | `VALIDATION_ERROR`, `UNKNOWN_SETTING` | Dữ liệu không hợp lệ |
| 429 | `RATE_LIMITED`, `LOGIN_LOCKED` | Kèm `Retry-After` |
| 503 | `MAINTENANCE_MODE`, `NOT_READY` | |
| 500 | `INTERNAL_ERROR` | Không lộ chi tiết, chỉ trả `request_id` để tra log |

## 10. Ánh xạ endpoint ↔ bước ↔ migration

| Nhóm | Bước | Migration cần |
|---|---|---|
| `/health`, `/ready` | A1 | |
| `/auth/register`, `/auth/login`, `/me` | A2 | `0001` |
| `/auth/refresh`, `/auth/logout*`, `/auth/guest` | A2 | `0002` |
| `/admin/users*`, `/admin/dashboard` | A3 | `0003` |
| `/admin/settings`, `/config/public` | A3 | `0004` |
| `/admin/audit-logs` | A3 | `0005` |
| `/rooms*`, `/admin/rooms*` | A4 | `0006` |
| `/turn-credentials` | A7 | |
| `/rooms/{code}/messages` | A8 | `0007` |
| `/metrics` | A11 | |
