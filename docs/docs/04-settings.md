# 04. Cấu hình (Settings)

> Cấu hình chia làm **hai loại**. Chỉ loại 2 mới có trên trang admin.

## 1. Hai loại cấu hình

| | Loại 1: Bí mật / hạ tầng | Loại 2: Vận hành |
|---|---|---|
| Ví dụ | `DATABASE_URL`, `JWT_SECRET`, `TURN_SECRET` | `allow_guest`, `max_participants_per_room` |
| Lưu ở | **Biến môi trường** (`.env`, GitHub Secrets) | Bảng `settings` trong DB (chỉ lưu giá trị bị ghi đè) |
| Đổi bằng | Sửa `.env` + restart container | Trang admin, **có hiệu lực ngay** |
| Hiện trên admin | **Không bao giờ** | Có |
| Ghi vào git | Chỉ `.env.example` (không có giá trị thật) | Không (nằm trong DB) |

## 2. Loại 1: Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `ENV` | Có | `dev` / `test` / `prod` |
| `DATABASE_URL` | Có | `postgresql+asyncpg://user:pass@db:5432/videocall` |
| `JWT_SECRET` | Có | ≥ 32 byte ngẫu nhiên. Đổi giá trị này sẽ làm mọi access token đang có mất hiệu lực |
| `TURN_SECRET` | Có | Dùng chung với `static-auth-secret` của coturn |
| `TURN_URLS` | Có trong app | Danh sách URL STUN/TURN cách nhau bằng dấu phẩy. Compose mặc định sinh từ `TURN_HOST` |
| `TURN_HOST` | Không | Địa chỉ IPv4 của máy dev để Compose ánh xạ cổng và coturn công bố địa chỉ relay. Mặc định `127.0.0.1` |
| `PUBLIC_BASE_URL` | Prod | `https://app.example.com` |
| `ALLOWED_ORIGINS` | Có | Danh sách origin cho CORS và Socket.io, phân tách bằng dấu phẩy |
| `FORWARDED_ALLOW_IPS` | Prod | IP của reverse proxy được tin cậy khi đọc `X-Forwarded-For` |
| `LOG_LEVEL` | Không | Mặc định `INFO` |
| `AVATAR_STORAGE_DIR` | Không | Chạy Python: `<repo>/.data/avatars`; Compose đặt `/var/lib/videocall/avatars` và mount volume `avatars` |
| `PROMETHEUS_URL` | Không | Để dashboard admin lấy băng thông TURN |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Có | Cho container Postgres |
| `ADMIN_ALLOWED_IPS` | Prod | Danh sách IP/CIDR được vào `/admin` (Caddy dùng) |

Quy tắc:
- `config.py` dùng `pydantic-settings`; **thiếu biến bắt buộc thì app không khởi động** (fail fast).
- `.env.example` liệt kê đủ biến, giá trị mẫu rõ ràng là giả (`change-me`).
- Secret sinh bằng `openssl rand -base64 48`.

## 3. Loại 2: Cấu hình vận hành

Cột "Áp dụng" cho biết thay đổi có tác dụng với đối tượng nào.

### 3.1 Truy cập (`access`)

| Khóa | Kiểu | Mặc định | Khoảng hợp lệ | Áp dụng | Mô tả |
|---|---|---|---|---|---|
| `allow_registration` | bool | `true` | | Request mới | Cho phép tự đăng ký |
| `allow_guest` | bool | `true` | | Kết nối mới | Cho phép vào bằng tên khách |
| `guest_ttl_minutes` | int | `120` | 10-1440 | Token mới | Thời hạn token khách |
| `maintenance_mode` | bool | `false` | | Ngay | Chặn **tạo phòng mới** và cấp token khách mới |
| `maintenance_message` | string | `""` | 0-200 ký tự | Ngay | Thông báo hiển thị khi bảo trì |
| `friends_enabled` | bool | `true` | | Request/sự kiện mới | E2/E3; tắt bạn bè, vẫn cho quản lý chặn và dọn quan hệ |
| `friend_search_enabled` | bool | `true` | | Request mới | Cho tìm email chính xác |
| `max_friends_per_user` | int | `200` | 10-2000 | Gửi/chấp nhận mới | Kiểm tra cả hai bên, tuần tự hóa thay đổi |
| `max_pending_friend_requests` | int | `50` | 5-500 | Gửi mới | Hạn mức người gửi, gồm lời mời từ chối bị che |
| `friend_request_ttl_days` | int | `30` | 1-365 | Đọc/chấp nhận và sweep | Hết hạn có hiệu lực ngay khi đọc; job cập nhật status khoảng 30 giây |

Hai cờ `friends_enabled` và `friend_search_enabled` có trong `/config/public`. Nhóm bạn bè được triển khai ở E2/E3 để áp dụng chính sách ngay; các phần quản trị còn lại thuộc E7.

E7 áp dụng các khóa `dm_enabled`, `dm_retention_days`, `invite_ttl_seconds`, `max_invites_per_call`, `call_history_enabled` và `call_history_retention_days` theo [bảng cấu hình V3](../docs_v3/extend.md#12-cấu-hình-mới-bổ-sung-04-settingsmd-mục-3). Public config có thêm hai cờ `dm_enabled` và `call_history_enabled`.

### 3.2 Phòng và chat (`rooms`)

| Khóa | Kiểu | Mặc định | Khoảng hợp lệ | Áp dụng | Mô tả |
|---|---|---|---|---|---|
| `max_participants_per_room` | int | `4` | 2-50 | Lượt vào mới | Trần cấu hình cho phòng mesh, trong giới hạn 4 người. Livestream có 1 suất phát và tối đa 4 người xem |
| `max_rooms_per_user` | int | `3` | 1-20 | Lần tạo mới | Số phòng đang mở tối đa của một user |
| `room_empty_ttl_seconds` | int | `300` | 30-86400 | Ngay | Phòng trống quá thời gian này sẽ tự đóng |
| `allow_screen_share` | bool | `true` | | Ngay (qua `features`) | Cho phép chia sẻ màn hình |
| `chat_enabled` | bool | `true` | | Tin nhắn mới | Cho phép chat |
| `chat_history_enabled` | bool | `true` | | Tin nhắn mới | Lưu lịch sử chat vào DB |
| `chat_retention_days` | int | `30` | 1-365 | Job dọn dẹp | Số ngày giữ chat của phòng đã đóng |

Về số người: mesh chịu được khoảng 4 người (mỗi máy upload N-1 luồng). Mặc định `4` phù hợp giai đoạn mesh; khi có SFU (A10) mới nâng lên.

### 3.3 Media (`media`)

| Khóa | Kiểu | Mặc định | Khoảng hợp lệ | Áp dụng | Mô tả |
|---|---|---|---|---|---|
| `max_video_bitrate_kbps` | int | `1500` | 100-8000 | Kết nối mới | Trần bitrate video camera |
| `max_screen_bitrate_kbps` | int | `2500` | 200-10000 | Kết nối mới | Trần bitrate chia sẻ màn hình |
| `max_video_resolution` | enum | `720p` | `360p`, `480p`, `720p`, `1080p` | Kết nối mới | Độ phân giải tối đa |
| `default_codec` | enum | `VP8` | `VP8`, `VP9`, `H264` | Kết nối mới | Codec video ưu tiên |
| `allow_avatar_upload` | bool | `true` | | Lần tải mới | Cho phép tải/thay ảnh đại diện; vẫn cho gỡ ảnh khi tắt |
| `avatar_max_kb` | int | `2048` | 100-5120 | Lần tải mới | Giới hạn tệp ảnh (KB); trả cùng `allow_avatar_upload` qua `/config/public` |

> **Lưu ý trung thực:** ở giai đoạn mesh, nhóm cấu hình này là **chính sách gửi cho client** (qua `media_policy`) và client tự áp dụng; một client sửa đổi có thể bỏ qua. Chỉ khi có SFU (A10) server mới ép được. Vì vậy đừng dùng nó để bảo vệ tài nguyên; việc bảo vệ băng thông TURN dựa vào giới hạn của coturn (xem `05-deployment.md`).

### 3.4 TURN (`turn`)

| Khóa | Kiểu | Mặc định | Khoảng hợp lệ | Áp dụng | Mô tả |
|---|---|---|---|---|---|
| `turn_enabled` | bool | `true` | | Request mới | `false` = `/turn-credentials` chỉ trả STUN |
| `turn_credential_ttl_seconds` | int | `14400` | 300-86400 | Credential mới | Thời hạn credential TURN (4 giờ) |
| `turn_allow_guests` | bool | `true` | | Request mới | Khách có được xin credential TURN không |

### 3.5 Bảo mật (`security`)

| Khóa | Kiểu | Mặc định | Khoảng hợp lệ | Áp dụng | Mô tả |
|---|---|---|---|---|---|
| `access_token_ttl_minutes` | int | `15` | 5-120 | Token mới | Thời hạn access token |
| `refresh_token_ttl_days` | int | `7` | 1-90 | Token mới | Thời hạn refresh token |
| `password_min_length` | int | `8` | 8-64 | Mật khẩu mới | Độ dài tối thiểu (tối đa cố định 128) |
| `login_max_attempts` | int | `5` | 3-20 | Ngay | Số lần đăng nhập sai trước khi khóa tạm |
| `login_lockout_minutes` | int | `15` | 1-1440 | Ngay | Thời gian khóa tạm |

### 3.6 Hằng số trong code (admin không sửa)

Các giới hạn mang tính bảo vệ hệ thống, đổi phải sửa code và qua review:

| Hằng số | Giá trị |
|---|---|
| Độ dài mật khẩu tối đa | 128 |
| Độ dài tin nhắn chat | 1-2000 |
| Kích thước SDP tối đa | 20 KB |
| Kích thước ICE candidate tối đa | 2 KB |
| Rate limit chat | 5 tin / 3 giây |
| Rate limit ICE | 200 / 10 giây |
| Giới hạn sai mật khẩu phòng | 5 lần / 5 phút |
| Cửa sổ khoan dung refresh token | 10 giây |

## 4. Cách triển khai (một nguồn sự thật)

```python
# services/settings_service.py (phác thảo)
class SettingsSchema(BaseModel):
    allow_guest: bool = Field(True, json_schema_extra={
        "category": "access", "description": "Cho phép đăng nhập bằng tên khách."})
    max_participants_per_room: int = Field(4, ge=2, le=50, json_schema_extra={
        "category": "rooms", "description": "Số người tối đa trong một phòng."})
    default_codec: Literal["VP8", "VP9", "H264"] = "VP8"
    ...
```

- `SettingsSchema` là **nguồn sự thật duy nhất**: kiểu, mặc định, khoảng hợp lệ, mô tả, nhóm. `GET /admin/settings` tự sinh danh sách từ đây; `PATCH` validate bằng đúng schema này.
- **Thêm một cấu hình mới = thêm một trường vào schema.** Không cần migration vì `settings.value` là `jsonb`.
- Đọc: `await settings_service.get()` trả một đối tượng `SettingsSchema` đã gộp (mặc định + ghi đè).

### Bộ nhớ đệm (cache)

- Giữ bản `SettingsSchema` đã gộp trong RAM, tránh truy vấn DB ở mỗi request/socket event.
- Khi admin `PATCH`: ghi DB + audit log (cùng transaction) → **xóa cache** → lần đọc kế tiếp nạp lại.
- v1 chạy một instance nên xóa cache là đủ. Nếu mở rộng nhiều instance: dùng TTL ngắn (30 giây) hoặc Redis pub/sub để báo xóa cache.

### Quy tắc `PATCH /admin/settings`

1. Gộp giá trị mới vào bản hiện tại, validate **toàn bộ** bằng `SettingsSchema`. Sai một khóa → 422, **không áp dụng gì**.
2. Khóa không tồn tại → 422 `UNKNOWN_SETTING`.
3. Giá trị `null` = reset: xóa dòng trong `settings`, về mặc định.
4. Chỉ lưu dòng khi giá trị **khác mặc định**.
5. Ghi một dòng audit log `settings.update` với `detail = { khóa: {before, after} }`.
6. Cấu hình không chứa thông tin nhạy cảm nên có thể ghi giá trị vào audit; nếu sau này thêm khóa nhạy cảm, đánh dấu `"secret": true` trong metadata và che giá trị trong audit.

## 5. Hiệu lực với trạng thái đang chạy

Nguyên tắc: **thay đổi cấu hình chỉ ảnh hưởng hành động mới, không đá người đang trong phòng.** Muốn ngắt phải dùng thao tác admin tường minh (đóng phòng, kick, khóa user).

| Thay đổi | Điều xảy ra |
|---|---|
| `maintenance_mode: true` | Không tạo được phòng mới, không cấp token khách mới. Phòng đang chạy và việc vào phòng sẵn có **vẫn bình thường**. Admin vẫn đăng nhập được |
| `allow_guest: false` | Không cấp token khách mới, kết nối socket mới của khách bị từ chối. Khách đang trong phòng **không bị ngắt** |
| `allow_registration: false` | Chặn đăng ký mới |
| `max_participants_per_room` giảm xuống thấp hơn số người đang có | Không ai bị đá; chỉ chặn người vào thêm |
| `chat_enabled: false` | Tin nhắn mới bị từ chối (`CHAT_DISABLED`); client nhận `features.chat = false` ở lần join sau |
| `turn_enabled: false` | `/turn-credentials` chỉ trả STUN. Credential TURN đã cấp vẫn dùng được tới hết hạn (coturn không biết) |
| Giảm `access_token_ttl_minutes` | Chỉ áp dụng token cấp sau đó |

## 6. Phần công khai cho client

`GET /api/v1/config/public` (không cần token) trả tập con an toàn:
`allow_registration`, `allow_guest`, `maintenance_mode`, `maintenance_message`, `password_min_length`, `allow_screen_share`, `chat_enabled`.

`media_policy` (`max_video_bitrate_kbps`, `max_screen_bitrate_kbps`, `max_video_resolution`, `default_codec`) và `features` được gửi trong ack của `join_room`, vì chỉ cần khi đã vào phòng.

## 7. Kiểm thử

- Unit: mỗi trường trong `SettingsSchema` có test biên (min/max, kiểu sai).
- Integration: `PATCH` hợp lệ có tác dụng ngay; `PATCH` sai một khóa không đổi gì; reset về mặc định; mỗi thay đổi tạo đúng một audit log; không-admin gọi → 403.
- Kiểm tra cache bị xóa sau `PATCH`.
