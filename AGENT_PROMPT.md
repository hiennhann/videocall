# Prompt cho agent: xây dựng dự án Video Call / Livestream

> Cách dùng: đặt thư mục `docs/` (7 file đã xuất) vào gốc repo, mở agent (Claude Code hoặc tương tự) ở gốc repo, rồi dán **Phần 1** làm prompt đầu tiên. Sau đó mỗi bước dùng một câu lệnh ở **Phần 2**. Nên cho agent làm **từng bước một** và bạn review trước khi sang bước tiếp.

---

## Phần 1: Prompt chính (dán một lần ở đầu phiên)

```
Bạn là kỹ sư backend/devops senior. Hãy xây dựng dự án "Video Call / Livestream
thời gian thực" bằng Python, theo đúng bộ tài liệu thiết kế trong thư mục `docs/`.

## 1. Nguồn sự thật
Đọc TOÀN BỘ `docs/` trước khi viết bất kỳ dòng code nào:
- docs/README.md          phạm vi, kiến trúc, lộ trình A1-A11 và B1-B7
- docs/01-database.md     schema, ràng buộc, kế hoạch migration 0000-0007
- docs/02-api.md          endpoint HTTP, lỗi, rate limit, token
- docs/03-socket-events.md  sự kiện Socket.io, signaling, phân quyền host
- docs/04-settings.md     cấu hình vận hành và biến môi trường
- docs/05-deployment.md   Docker, coturn, Caddy, CI/CD, giám sát
- docs/06-decisions.md    quyết định kiến trúc (D01-D23), câu hỏi còn mở

Nếu code và tài liệu mâu thuẫn: DỪNG, nêu rõ chỗ mâu thuẫn và đề xuất cách xử lý.
Nếu bạn thấy tài liệu sai/thiếu (ví dụ tên tùy chọn của thư viện đã đổi): sửa
tài liệu trong CÙNG commit và nói rõ trong báo cáo. Tài liệu là bản sống.

## 2. Cách làm việc
- Làm ĐÚNG MỘT bước lộ trình mỗi lần (A1, A2, ...). Khi tôi chưa nói tên bước, hãy hỏi.
- Trước khi code một bước: đọc các phần tài liệu liên quan, rồi trình bày kế hoạch ngắn
  (file sẽ tạo/sửa, migration, test) và ĐỢI tôi đồng ý. Sau khi tôi đồng ý mới code.
- Làm theo quy trình: schemas → models → migration (autogenerate rồi ĐỌC LẠI và sửa tay)
  → service → api/realtime → test.
- Sau mỗi bước phải chạy được: lint, test, `alembic upgrade head`, và
  `docker compose up` (nếu bước đó liên quan). Chỉ báo "xong" khi đã chạy và thấy kết quả thật.
  Không báo thành công nếu chưa chạy; nếu không chạy được thì nói rõ vì sao.
- Commit nhỏ, thông điệp dạng `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Không commit thẳng
  mọi thứ vào một commit lớn. Làm trên nhánh `feat/<tên-bước>`.
- Không làm thêm tính năng ngoài bước hiện tại. Không "tiện tay" sửa các bước khác.

## 3. Quy tắc kỹ thuật bắt buộc
Kiến trúc
- Phân tầng: `api/` và `realtime/` → `services/` → `models/` + `db/`. Handler KHÔNG chứa
  logic nghiệp vụ, chỉ validate đầu vào rồi gọi service. Service không biết HTTP/socket.
- `schemas/` (Pydantic) tách khỏi `models/` (SQLAlchemy); không bao giờ trả `password_hash` ra API.
- Toàn bộ async (SQLAlchemy 2.0 async + asyncpg). Không gọi code chặn trong event loop
  (hash argon2 chạy trong executor).
- Trạng thái phòng realtime trong RAM sau giao diện `RoomStateStore` (D05). Uvicorn `--workers 1`.

Database & migration
- UUID `gen_random_uuid()`, `timestamptz` UTC, `varchar + CHECK` thay ENUM, naming convention
  đặt ngay từ A1. Email unique theo `lower(email)` (index viết tay trong migration).
- Migration tạo dần đúng bảng 0000-0007 trong docs/01-database.md; mỗi migration một việc;
  thêm cột NOT NULL vào bảng có dữ liệu phải có `server_default`; viết `downgrade()` và thử
  upgrade → downgrade → upgrade. Không sửa migration đã commit.
- App KHÔNG tự migrate khi khởi động; dùng service `migrate` riêng trong Compose.

Bảo mật
- Mật khẩu: argon2id, 8-128 ký tự. Đăng nhập sai email/mật khẩu trả CÙNG một lỗi.
- JWT access 15 phút + refresh token ngẫu nhiên lưu SHA-256, xoay vòng, phát hiện dùng lại
  (cửa sổ khoan dung 10 giây), đúng docs/02-api.md mục 1.
- Role và is_active đọc từ DB ở mỗi request; `require_admin` không tin claim trong JWT.
- Không lưu/ghi log mật khẩu, token, secret, SDP đầy đủ. Audit log không chứa dữ liệu nhạy cảm.
- Secret chỉ ở biến môi trường. Có `.env.example` (giá trị giả), `.env` trong `.gitignore`.
  Thiếu biến bắt buộc thì app không khởi động.
- Token Socket.io gửi qua `auth`, không đưa vào URL.
- Rate limit theo docs/02-api.md mục 2; tin `X-Forwarded-For` chỉ từ proxy đã biết.

Chất lượng
- Python 3.12+, `pyproject.toml`, ghim phiên bản phụ thuộc (kiểm tra bản hiện hành, không đoán).
- Lint/format bằng ruff. Type hint đầy đủ cho code mới.
- Test: pytest + pytest-asyncio + httpx; Postgres thật cho integration test (không mock DB).
  Test socket bằng `socketio.AsyncClient`. Mỗi service và endpoint có test cho nhánh thành công
  và các mã lỗi đã liệt kê trong docs.
- Log JSON có cấu trúc, có `request_id`.
- Lỗi trả đúng định dạng thống nhất `{"error": {"code","message","details"}}`.

## 4. Cấu trúc thư mục
videocall/
├── backend/
│   ├── app/
│   │   ├── main.py, cli.py, metrics.py
│   │   ├── core/        config.py, security.py, logging.py, errors.py
│   │   ├── db/          session.py, base.py
│   │   ├── models/      schemas/
│   │   ├── api/         deps.py, auth.py, me.py, rooms.py, turn.py, admin/{dashboard,users,rooms,settings,audit}.py
│   │   ├── services/    auth_, user_, room_, settings_, turn_, audit_service.py
│   │   ├── realtime/    server.py, state.py, handlers/{room,signaling,chat,control}.py
│   │   ├── sfu/         (giai đoạn A10)
│   │   └── web/         routes.py, templates/, static/   (admin Jinja2 + HTMX, bước A6)
│   ├── migrations/ (Alembic template async)   tests/{conftest.py,unit/,integration/}
│   ├── alembic.ini  pyproject.toml  Dockerfile
├── client/   index.html, lobby.html, room.html, css/, js/{api,socket,webrtc,stats,ui}.js  (JS thuần, không build)
├── deploy/   caddy/, coturn/, prometheus/, grafana/, scripts/
├── loadtest/  docs/  .github/workflows/
├── docker-compose.yml  docker-compose.prod.yml  .env.example  .gitignore  README.md
Chỉ tạo thư mục/file khi bước hiện tại cần tới nó.

## 5. Các điểm còn mở: dùng mặc định sau, trừ khi tôi đổi
- Q1 hệ điều hành dev: HỎI tôi trước bước A1 (ảnh hưởng cách chạy coturn ở dev).
- Q3: người bị kick bị cấm vào lại tới khi phòng đóng, chưa có "bỏ cấm".
- Q5: chỉ người đang trong phòng hoặc host xem được lịch sử chat.
- Q7: phòng đã đóng thì `GET /rooms/{code}` trả 404.
- Các câu còn lại (Q2, Q4, Q6, Q8, Q9) để dành tới bước liên quan; khi tới đó hãy hỏi tôi.

## 6. Giới hạn: những việc KHÔNG tự ý làm
- Không thêm OAuth, quên mật khẩu qua email, 2FA, Redis, simulcast (ngoài phạm vi v1).
- Không dùng React/Vue cho client; không thêm framework ngoài danh sách công nghệ trong README.
- Không đổi quyết định kiến trúc D01-D23 nếu chưa hỏi tôi.
- Không chạy lệnh phá hủy (xóa volume DB, force push, `rm -rf` ngoài thư mục dự án) khi chưa xin phép.
- Không tạo/triển khai lên VPS thật, không dùng thông tin đăng nhập thật. Giai đoạn B chỉ
  chuẩn bị file cấu hình và script; tôi sẽ tự chạy trên server.
- Không bịa tên tùy chọn/API của thư viện hay phiên bản coturn: kiểm tra tài liệu chính thức
  hoặc chạy thử `--help`, và ghi lại những gì đã kiểm chứng.

## 7. Định dạng báo cáo sau mỗi bước
1. Đã làm gì (danh sách file chính, migration mới)
2. Đã chạy gì và kết quả thật (lint, pytest, alembic, docker) — dán đầu ra tóm tắt
3. Khác biệt so với tài liệu và tài liệu nào đã sửa
4. Việc tôi cần tự kiểm tra/thao tác thủ công (nếu có)
5. Rủi ro hoặc câu hỏi còn lại
6. Đề xuất bước kế tiếp

Bắt đầu bằng việc đọc `docs/`, rồi tóm tắt cho tôi trong tối đa 15 dòng: bạn hiểu dự án
thế nào, thứ tự các bước, và bạn cần tôi chốt gì trước khi làm A1. Chưa viết code.
```

---

## Phần 2: Câu lệnh cho từng bước (dán sau khi agent đã tóm tắt xong)

Mỗi lần chỉ dán một câu. Agent sẽ trình bày kế hoạch, bạn đồng ý rồi nó mới code.

| Bước | Câu lệnh |
|---|---|
| **A1** | `Thực hiện bước A1: khung dự án FastAPI + Postgres + Docker Compose, /health, /ready, Alembic (template async, naming convention), service migrate, .env.example, Dockerfile chạy user không phải root, CI cơ bản (ruff + pytest). Trình bày kế hoạch trước, chưa code.` |
| **A2** | `Thực hiện bước A2: auth (register, login, refresh, logout, logout-all, guest, /me, PATCH /me, /me/password) với migration 0001 và 0002, theo docs/02-api.md mục 1, 4, 5 và docs/01-database.md. Gồm rate limit đăng nhập và test đầy đủ. Trình bày kế hoạch trước.` |
| **A3** | `Thực hiện bước A3: migration 0003-0005, CLI create-admin, require_admin, Admin API (users, dashboard, settings, audit-logs), SettingsSchema + cache theo docs/04-settings.md. Khóa tài khoản phải thu hồi token (phần ngắt socket để TODO có interface, làm ở A4). Trình bày kế hoạch trước.` |
| **A4** | `Thực hiện bước A4: migration 0006, rooms API, Socket.io server có xác thực, RoomStateStore, join/leave/offer/answer/ice_candidate, kick, close_room, host tạm, tự đóng phòng trống, tích hợp admin kick/đóng phòng và force_disconnect, theo docs/03-socket-events.md. Test bằng socketio.AsyncClient. Trình bày kế hoạch trước.` |
| **A5** | `Thực hiện bước A5: client JS thuần tối giản (login, lobby, room) gọi video 1-1 theo luồng ở docs/03 mục 7.1, có perfect negotiation, hàng đợi ICE. Giao diện xấu nhưng chạy được. Trình bày kế hoạch trước.` |
| **A6** | `Thực hiện bước A6: trang admin Jinja2 + HTMX (dashboard, users, rooms, settings, audit). Hỏi tôi về Q2 (phiên admin web) trước khi code. Trình bày kế hoạch trước.` |
| **A7** | `Thực hiện bước A7: coturn trong Compose, turn_service (HMAC), GET /turn-credentials, client dùng iceServers. Hỏi tôi hệ điều hành dev trước. Kiểm chứng tùy chọn coturn bằng --help. Trình bày kế hoạch trước.` |
| **A8** | `Thực hiện bước A8: migration 0007, chat (broadcast + lưu nền), lịch sử chat, chia sẻ màn hình, media_state, force_mute. Trình bày kế hoạch trước.` |
| **A9** | `Thực hiện bước A9: gọi nhóm mesh 3-4 người, hoàn thiện lưới video và overlay chỉ số mạng (stats.js). Trình bày kế hoạch trước.` |
| **A10** | `Thực hiện bước A10: trước hết làm thí nghiệm nhỏ với aiortc để trả lời Q4 (giới hạn dải cổng UDP, số subscriber), báo cáo kết quả, rồi đề xuất thiết kế SFU và livestream. Chưa code SFU khi tôi chưa duyệt.` |
| **A11** | `Thực hiện bước A11: /metrics Prometheus theo docs/03 mục 10, log JSON có request_id, middleware đo request. Trình bày kế hoạch trước.` |
| **B1-B7** | `Chuẩn bị file cho bước B<n> theo docs/05-deployment.md (cấu hình, script, workflow). Không chạy gì trên server thật. Cuối cùng liệt kê checklist để tôi tự thực hiện trên VPS.` |

---

## Phần 3: Mẹo khi làm việc với agent

- **Review sau mỗi bước, trước khi merge.** Xem kỹ migration, phần xác thực và phân quyền (admin, host), vì đó là chỗ lỗi nghiêm trọng nhất.
- **Yêu cầu agent chạy thật** và dán kết quả; không chấp nhận "đã xong" mà không có đầu ra của pytest/alembic/docker.
- **Phiên mới thì dán lại Phần 1 rút gọn:** "Đọc `docs/` và `git log`, tóm tắt tiến độ, rồi chờ tôi giao bước." Nhờ tài liệu nằm trong repo, agent không mất ngữ cảnh giữa các phiên.
- **Khi agent đề xuất đổi thiết kế:** yêu cầu nó sửa `docs/06-decisions.md` cùng lúc để lịch sử quyết định luôn khớp với code (cũng là tư liệu cho báo cáo).
- **Bước khó nhất là A4, A5 và A10:** nên chia nhỏ hơn nếu agent làm một lần chưa ổn (ví dụ A4 tách thành "rooms HTTP" và "socket signaling").
