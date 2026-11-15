# Video Call / Livestream

Backend Python cho dự án gọi video thời gian thực. A1 cung cấp khung FastAPI, PostgreSQL 16, Alembic và Docker Compose. Xem [tài liệu thiết kế](docs/docs/README.md) để biết lộ trình.

## Chạy trên Windows

Mở Docker Desktop. Chạy các lệnh sau trong PowerShell tại thư mục dự án. Tạo `.env` từ mẫu ở lần chạy đầu tiên.

```powershell
Copy-Item .env.example .env
docker compose up --build --wait
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
```

`/health` kiểm tra process. `/ready` trả `200` khi kết nối được PostgreSQL và Alembic đã ở `head`, hoặc `503` nếu app chưa sẵn sàng. Compose chạy `migrate` trước `app`. Tài khoản ứng dụng và tài khoản migration dùng hai URL riêng. Các giá trị trong `.env.example` dành cho môi trường dev.

```powershell
docker compose ps -a
docker compose logs migrate app
docker compose stop
```

## Kiểm thử backend với Python 3.12

Đặt `DATABASE_URL` trỏ tới PostgreSQL thử nghiệm bằng tài khoản có quyền chạy migration. Đặt `TEST_DATABASE_URL` trỏ tới cùng database bằng tài khoản có quyền đọc `alembic_version`. Các lệnh chạy trong thư mục `backend/`.

```powershell
python -m pip install -e '.[test]'
ruff check .
ruff format --check .
alembic upgrade head
alembic check
pytest --cov=app
```
