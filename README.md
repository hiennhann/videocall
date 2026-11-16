# Video Call / Livestream

Backend Python cho dự án gọi video thời gian thực. A1 cung cấp khung FastAPI, PostgreSQL 16, Alembic và Docker Compose. A2 thêm API xác thực và hồ sơ. A3 thêm quản trị và cấu hình. A4 thêm phòng và signaling Socket.IO. Xem [tài liệu thiết kế](docs/docs/README.md) để biết lộ trình.

## Chạy trên Windows

Mở Docker Desktop. Chạy các lệnh sau trong PowerShell tại thư mục dự án. Tạo `.env` từ mẫu ở lần chạy đầu tiên.

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

`/health` kiểm tra process. `/ready` trả `200` khi kết nối được PostgreSQL và Alembic đã ở `head`, hoặc `503` nếu app chưa sẵn sàng. Compose chạy `migrate` trước `app`. Tài khoản ứng dụng và tài khoản migration dùng hai URL riêng. Các giá trị trong `.env.example` dành cho môi trường dev.

Mở [Videocall](http://localhost:8000/) để tạo tài khoản, đăng nhập và tạo phòng gọi 1–1. Mở một cửa sổ ẩn danh hoặc trình duyệt khác, đăng nhập bằng tài khoản khác hoặc tên khách, rồi nhập mã phòng. Bấm **Vào phòng và bật camera** ở cả hai phiên. WebRTC có thể chọn relay TURN khi đường trực tiếp không thông.

Nếu đang dùng `.env` từ A6, bỏ dòng mẫu `TURN_URLS=stun:turn.example.com:3478` để Compose dùng coturn cục bộ. Xem [cấu hình và cách kiểm tra relay](docs/docs/05-deployment.md#44-chạy-coturn-ở-môi-trường-dev).

Ở A8, gửi tin trong mục **Tin nhắn** và chọn **Tin nhắn cũ hơn** nếu phòng có thêm lịch sử. Dùng **Chia sẻ màn hình** để gửi thêm một luồng bên cạnh camera. Host thấy nút tắt mic và camera của người đang gọi cùng.

Swagger vẫn có tại [`/docs`](http://localhost:8000/docs) để thử API.

Tạo quản trị viên A3 bằng lệnh sau. Nhập mật khẩu hai lần khi được hỏi, rồi đăng nhập qua `/api/v1/auth/login` để dùng các API `/api/v1/admin`.

```powershell
docker compose exec app python -m app.cli create-admin --email admin@example.com
```

Ở A4, dùng `POST /api/v1/rooms` trong Swagger để tạo phòng. Client Socket.IO kết nối tới `http://localhost:8000` tại `/socket.io`, gửi `auth: { token: accessToken }` khi kết nối và gọi `join_room` với mã phòng. Giữ Uvicorn ở một worker để mọi kết nối dùng chung trạng thái phòng.

Ở A6, mở [trang quản trị](http://localhost:8000/admin), rồi đăng nhập bằng tài khoản admin vừa tạo. Từ đây có thể quản lý người dùng, phòng, cấu hình và xem nhật ký. Trình duyệt tự làm mới phiên qua cookie giới hạn ở `/admin`. Khi triển khai ngoài localhost, dùng HTTPS.

```powershell
docker compose ps -a
docker compose logs migrate app
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
docker compose stop
```

## Kiểm thử backend với Python 3.12

Đặt `DATABASE_URL` trỏ tới PostgreSQL thử nghiệm bằng tài khoản có quyền chạy migration. Đặt `TEST_DATABASE_URL` trỏ tới cùng database bằng tài khoản có quyền đọc `alembic_version` và đọc, thêm, cập nhật bảng `users`, `refresh_tokens`. Khi dùng tài khoản app riêng, đặt `POSTGRES_APP_USER` thành tên role đã tạo để Alembic cấp quyền vào hai bảng mới. Suite integration tạo dữ liệu giả trong database này. Các lệnh chạy trong thư mục `backend/`.

```powershell
python -m pip install -e '.[test]'
ruff check .
ruff format --check .
alembic upgrade head
alembic check
pytest --cov=app
```
