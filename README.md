# Videocall

Ứng dụng web gọi video nhóm, livestream và nhắn tin. Web người dùng và web quản trị dùng chung FastAPI, PostgreSQL, Socket.IO và WebRTC. Xem [tài liệu kiến trúc](docs/docs/README.md).

## Chạy trên Windows

Mở Docker Desktop rồi chạy PowerShell tại thư mục dự án. Lệnh đầu tạo `.env` nếu chưa có.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\tools\start-docker.ps1
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

`/health` kiểm tra process. `/ready` trả `200` khi kết nối được PostgreSQL và Alembic đã ở `head`, hoặc `503` nếu app chưa sẵn sàng. Compose chạy `migrate` trước `app`. Lệnh khởi động tự dọn container `migrate` sau khi các dịch vụ sẵn sàng. PostgreSQL, web app, Coturn và SFU tiếp tục phục vụ web, gọi và livestream. Tài khoản ứng dụng và tài khoản migration dùng hai URL riêng.

Dùng `.\tools\start-docker.ps1 -NoBuild` khi đã có image muốn chạy. Nếu đã cấu hình `.lan/compose.yml` cho HTTPS nội bộ, chạy `.\tools\start-docker.ps1 -Lan` để bật thêm proxy Caddy cho điện thoại.

## Web người dùng

Mở [Videocall](http://localhost:8000/) để đăng ký hoặc đăng nhập. Máy chủ kiểm tra phiên trước khi trả trang nội bộ. Người dùng có thể vào bằng tên khách khi quản trị viên bật tính năng này.

1. Thiết bị thứ nhất chọn **Tạo phòng** và bấm **Vào phòng** ở màn hình chuẩn bị.
2. Thiết bị thứ hai đăng nhập bằng tài khoản khác hoặc dùng tên khách. Chọn **Vào phòng**, nhập mã được chia sẻ, bấm **Tiếp tục**, rồi bấm **Vào phòng** ở màn hình chuẩn bị.
3. Trong cuộc gọi, thử mic, camera, chat, chia sẻ màn hình và **Chỉ số mạng**. Với phòng livestream, host bấm **Bắt đầu phát** để người xem nhận tiếng và hình.

Các trang [Bạn bè](http://localhost:8000/friends), [Tin nhắn](http://localhost:8000/messages), [Lịch sử](http://localhost:8000/history) và [Tài khoản](http://localhost:8000/account) dành cho thành viên. Khi thử trên điện thoại, mở URL HTTPS mà điện thoại truy cập được. Xem [cấu hình TURN và SFU](docs/docs/05-deployment.md), [nghiệm thu luồng gọi](docs/docs_v3/u2-u3-report.md) và [nghiệm thu giao diện V3](docs/docs_v3/u4-u7-report.md).

## Web quản trị

Tạo tài khoản quản trị rồi đăng nhập vào [web quản trị](http://localhost:8000/admin). Dashboard hiển thị phòng và tài khoản đang hoạt động. Quản trị viên có thể quản lý phòng, tài khoản, cấu hình, nhật ký và xuất báo cáo CSV.

```powershell
docker compose exec app python -m app.cli create-admin --email admin@example.com
```

Trong môi trường dev cục bộ, có thể dùng `docker compose exec app python -m app.cli create-demo-admin` rồi đăng nhập bằng `admin` và mật khẩu `admin123`.

## Vận hành và kiểm tra

Migration hiện tại là `0013`. Swagger có tại [`/docs`](http://localhost:8000/docs). Trong môi trường dev, [`/metrics`](http://localhost:8000/metrics) trả chỉ số Prometheus và [`/styleguide`](http://localhost:8000/styleguide) hiển thị các thành phần giao diện. Dùng `X-Request-ID` để đối chiếu yêu cầu với nhật ký của app. Giữ Uvicorn ở một worker để dùng chung trạng thái phòng.

```powershell
docker compose ps -a
docker compose logs migrate app
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
docker compose stop
```

App React Native được lưu cho đợt phát triển sau. Mobile CI có thể chạy thủ công khi cần tạo bản cài. [Kế hoạch app](docs/docs_v2/08-app-mobile-sau-nay.md)

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
