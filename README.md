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

Mở [Videocall](http://localhost:8000/) để tạo tài khoản, đăng nhập và tạo phòng gọi tối đa bốn người. Dùng một phiên trình duyệt riêng cho mỗi tài khoản hoặc khách, rồi nhập mã phòng. Bấm **Vào phòng và bật camera** ở từng phiên. WebRTC có thể chọn relay TURN khi đường trực tiếp không thông. Trong phòng, bật **Chỉ số mạng** để xem RTT, jitter, mất gói, bitrate, FPS và đường kết nối của từng người.

Nếu đang dùng `.env` từ A6, bỏ dòng mẫu `TURN_URLS=stun:turn.example.com:3478` để Compose dùng coturn cục bộ. Xem [cấu hình và cách kiểm tra relay](docs/docs/05-deployment.md#44-chạy-coturn-ở-môi-trường-dev).

Ở A8, gửi tin trong mục **Tin nhắn** và chọn **Tin nhắn cũ hơn** nếu phòng có thêm lịch sử. Dùng **Chia sẻ màn hình** để gửi thêm một luồng bên cạnh camera. Host thấy nút tắt mic và camera của người đang gọi cùng.

Để phát **livestream**, chọn loại phòng **Livestream** trong lobby. Host bấm **Bắt đầu phát** rồi gửi mã phòng cho tối đa bốn người xem. Trình duyệt chỉ xin quyền camera và mic khi người được chọn bấm phát. Host có thể đổi người phát trong mục **Người được phát**. [Cấu hình SFU dev](docs/docs/05-deployment.md#46-sfu-livestream-trong-compose)

Swagger vẫn có tại [`/docs`](http://localhost:8000/docs) để thử API.

V3 E1 bổ sung API hồ sơ và ảnh đại diện ([báo cáo E1](docs/docs_v3/e1-report.md), migration `0009`, volume `avatars`). E2/E3 bổ sung API bạn bè/chặn và thông báo realtime, ẩn hiện online, đồng bộ sau khi kết nối lại ([báo cáo và cách nghiệm thu E2/E3](docs/docs_v3/e2-e3-report.md), migration `0010`, nhánh `feat/phase2`). Giao diện Bạn bè thuộc U5, chỉnh hồ sơ thuộc U6; E4–E7 vẫn là các bước tiếp theo.

Trong môi trường dev, [`/metrics`](http://localhost:8000/metrics) trả chỉ số HTTP, Socket.IO và phòng ở định dạng Prometheus. Xem log JSON bằng `docker compose logs app` và tra từng yêu cầu bằng header `X-Request-ID`.

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

## Thử V2 ở môi trường dev

Chạy Docker Compose ở thư mục dự án rồi tạo tài khoản quản trị demo lần đầu.

```powershell
docker compose exec app python -m app.cli create-demo-admin
```

Đăng nhập [trang quản trị](http://localhost:8000/admin/login) bằng `admin` và mật khẩu `admin123` trong môi trường dev cục bộ. Tài khoản đã có có thể đăng nhập lại sau khi nâng cấp từ V1. Dùng hai tài khoản khác nhau khi thử gọi giữa hai thiết bị, và dùng một tài khoản khi thử chuyển thiết bị.

Điện thoại kiểm thử bằng web trên trình duyệt qua HTTPS. App React Native được lưu để phát triển sau. Xem [kế hoạch app](docs/docs_v2/08-app-mobile-sau-nay.md) và [ma trận nghiệm thu V2](docs/docs_v2/06-trien-khai.md).

## Nền tảng UI V3

Giao diện V3 đã áp dụng cho [web người dùng](http://localhost:8000/) và [web quản trị](http://localhost:8000/admin), dùng chung màu, phông và thành phần đã duyệt; có sáng/tối/theo hệ thống và bố cục cho điện thoại. Chạy lại `docker compose up --build --wait` để cập nhật. Xem [báo cáo tích hợp và ảnh kiểm tra](docs/docs_v3/ui-integration-report.md). Trang [mẫu U1](http://localhost:8000/styleguide) tiếp tục có khi `ENV=dev`.

Các mục người dùng mở trang riêng: [Trang chủ](http://localhost:8000/lobby), [Phòng của tôi](http://localhost:8000/rooms), [Tài khoản](http://localhost:8000/account), [Vào phòng](http://localhost:8000/rooms/join), [Tạo phòng](http://localhost:8000/rooms/create). Mỗi trang chỉ chứa nội dung của mục đó; Chat/Thành viên tiếp tục nằm trong phòng gọi. Xem [báo cáo tách trang](docs/docs_v3/navigation-pages-report.md).

Mở [trang đăng nhập](http://localhost:8000/) để bắt đầu. Nếu mở trực tiếp một trang khi chưa có phiên, hệ thống chuyển sang đăng nhập rồi quay lại đúng trang đã yêu cầu. Đăng xuất sẽ trở về trang đăng nhập.

Cả web người dùng và quản trị đều kiểm tra phiên ở máy chủ trước khi trả trang nội bộ, kể cả khi mở URL HTML trực tiếp. Web người dùng cho phép tài khoản hoặc phiên tên khách; web quản trị chỉ cho admin. Cookie trang được xóa khi đăng xuất, và phiên đã thu hồi không mở lại được trang.

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
