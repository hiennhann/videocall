# Video Call / Livestream

Backend Python cho dự án gọi video thời gian thực. A1 cung cấp khung FastAPI, PostgreSQL 16, Alembic và Docker Compose. A2 thêm API xác thực và hồ sơ. Xem [tài liệu thiết kế](docs/docs/README.md) để biết lộ trình.

## Chạy trên Windows

Mở Docker Desktop. Chạy các lệnh sau trong PowerShell tại thư mục dự án. Tạo `.env` từ mẫu ở lần chạy đầu tiên.

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

`/health` kiểm tra process. `/ready` trả `200` khi kết nối được PostgreSQL và Alembic đã ở `head`, hoặc `503` nếu app chưa sẵn sàng. Compose chạy `migrate` trước `app`. Tài khoản ứng dụng và tài khoản migration dùng hai URL riêng. Các giá trị trong `.env.example` dành cho môi trường dev.

Mở [Swagger UI](http://localhost:8000/docs) để gọi `POST /api/v1/auth/register` rồi `POST /api/v1/auth/login`. Dùng nút **Authorize** với `access_token` để gọi `GET /api/v1/me`.

Tạo quản trị viên A3 bằng lệnh sau. Nhập mật khẩu hai lần khi được hỏi, rồi đăng nhập qua `/api/v1/auth/login` để dùng các API `/api/v1/admin`.

```powershell
docker compose exec app python -m app.cli create-admin --email admin@example.com
```

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
