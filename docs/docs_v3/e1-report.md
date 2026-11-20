# E1 — Hồ sơ cá nhân và ảnh đại diện

Ngày triển khai: 20/11/2026. E1 ban đầu làm tại `feat/update-ui-v3`, sau đó được lưu thành commit `e0ce967` trên `feat/phase2` làm nền cho E2/E3 theo yêu cầu tiếp theo.

Phạm vi được yêu cầu: **chỉ E1, dừng để người dùng kiểm tra và duyệt**. E2–E7 chưa triển khai. Giao diện chỉnh hồ sơ/upload thuộc U6 trong lộ trình, chưa thêm vào hai web ở E1.

## 1. Thiết kế và phạm vi đã thực hiện

| Nhóm | Tệp chính | Thay đổi |
|---|---|---|
| Dữ liệu | `backend/migrations/versions/0009_add_user_profile.py`, `backend/app/models/user.py` | Thêm ngày sinh, hash ảnh, thời điểm cập nhật ảnh, hai quyền riêng tư. NULL/default tương thích tài khoản cũ; không sửa migration đã có. |
| Hợp đồng hồ sơ | `backend/app/schemas/auth.py`, `backend/app/api/me.py`, `backend/app/services/user_service.py` | GET/PATCH hồ sơ, cập nhật từng trường, kiểm tra ngày sinh, email bất biến; giữ API mật khẩu và hồ sơ khách. |
| Ảnh | `backend/app/services/avatar_service.py`, `backend/app/api/media.py` | Kiểm tra định dạng thực, giới hạn dung lượng/pixel, xoay EXIF, bỏ metadata, cắt giữa, hai ảnh WebP, ghi tệp nguyên tử, thay/gỡ và cache theo hash. |
| Tích hợp | `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/schemas/settings.py` | Đăng ký service/tuyến media, thêm CORS PUT, đường dẫn lưu, hai cấu hình tải ảnh. |
| Tên trong phòng | `backend/app/services/room_service.py` | Lấy tên DB khi bắt đầu lượt vào phòng; cuộc gọi hiện tại giữ tên lúc vào, kể cả JWT vẫn chứa tên cũ. |
| Chạy Docker | `backend/Dockerfile`, `docker-compose.yml` | Thư mục thuộc user không phải root; volume `avatars` giữ ảnh khi tạo lại container. |
| Kiểm thử | `backend/tests/unit/test_avatar.py`, `backend/tests/integration/test_profile.py`, `backend/tests/integration/test_rooms_socket.py` | Ảnh an toàn, API hồ sơ, phân quyền, yêu cầu đồng thời, lỗi ghi đĩa, luồng đổi tên. |

Các quy tắc nghiệp vụ/định quyền được kiểm tra ở service. API chỉ nhận dữ liệu của chính tài khoản đã xác thực, không nhận `user_id`, `email`, `role` để sửa hồ sơ.

## 2. Hợp đồng sử dụng

| Yêu cầu | Kết quả |
|---|---|
| `GET /api/v1/me` | Hồ sơ cũ + `birth_date`, `avatar_url`, `avatar_thumb_url`, `privacy` cho thành viên |
| `PATCH /api/v1/me` | Sửa riêng tên, ngày sinh hoặc từng quyền; trường không gửi giữ nguyên; `birth_date: null` để xóa |
| `PUT /api/v1/me/avatar` | Multipart, trường `file`, trả hồ sơ chứa hai URL ảnh |
| `DELETE /api/v1/me/avatar` | 204, gỡ cả hai ảnh, gọi lại vẫn thành công |
| `GET /media/avatars/{user_id}/{hash}-{size}.webp` | Ảnh công khai theo URL băm, cỡ 256/64, cache 1 năm; tệp không có trả 404 |

Ví dụ PATCH:

```json
{
  "display_name": "Nguyễn An",
  "birth_date": "2004-05-20",
  "privacy": { "discoverable_by_email": false, "show_online_status": false }
}
```

Tên được trim, loại ký tự điều khiển, dài 2–50 ký tự. Ngày sinh tùy chọn, định dạng `YYYY-MM-DD`, không ở tương lai (theo ngày UTC), không trước 1900 và không sớm hơn ngày hiện tại trừ 120 năm. Không áp dụng tuổi tối thiểu. Email giữ nguyên; cập nhật email/quyền tài khoản qua PATCH hồ sơ bị từ chối.

Khách vẫn dùng GET hồ sơ và vào phòng như trước; sửa hồ sơ/tải/gỡ ảnh trả `GUEST_NOT_ALLOWED`. Tài khoản bị khóa hoặc cần đổi mật khẩu bắt buộc không được sửa hồ sơ/ảnh. Mật khẩu vẫn thay bằng API hiện có.

## 3. Lưu ảnh và giới hạn

- JPEG, PNG hoặc WebP được kiểm tra theo nội dung, kể cả tên/MIME gửi lên sai. SVG, GIF, tệp hỏng bị từ chối. Ảnh động dùng khung đầu và xuất ảnh tĩnh.
- `avatar_max_kb = 2048`, admin chỉnh được trong khoảng 100–5120 KB; tối đa 25 triệu pixel. Toàn bộ body multipart còn có trần phụ 16 KB cho header/boundary; tệp tạm được đóng khi xử lý lỗi.
- Xác thực và kiểm tra `allow_avatar_upload` trước khi đọc body. Tắt upload vẫn cho gỡ ảnh cũ.
- Pillow 13.0.0 chạy trong thread pool, semaphore tối đa hai tác vụ giải mã/xử lý. Chỉ tạo ảnh sạch sau khi thu nhỏ để giảm bộ nhớ.
- Áp dụng hướng EXIF trước khi cắt giữa; ảnh mới chỉ chứa pixel, bỏ EXIF/GPS/XMP/ICC. Xuất WebP 256×256 và 64×64.
- Tên tệp là SHA-256 của hai đầu ra; không dùng tên tệp người dùng. Ghi tạm rồi đổi tên, chỉ cập nhật DB sau khi đủ hai ảnh. Tuần tự hóa thay/gỡ qua commit và dọn tệp trong kiến trúc một worker hiện có.
- Nếu ghi đĩa thất bại, rollback DB và dọn tệp mới. Nếu commit thất bại nhưng không xác định được DB đã nhận hay chưa, giữ tệp mới để tránh mất ảnh; dọn tệp mồ côi cần tác vụ vận hành sau này.
- Compose lưu ở volume `avatars:/var/lib/videocall/avatars`. Chạy Python trực tiếp mặc định `<repo>/.data/avatars`; có thể đặt `AVATAR_STORAGE_DIR`. Thư mục ảnh được bỏ qua bởi Git.
- URL ảnh là công khai theo thiết kế, không chứa email/ngày sinh. Cache trình duyệt có thể giữ ảnh đã tải dù ảnh đã bị xóa trên máy chủ. Hướng dẫn backup/restore DB cùng volume nằm ở `docs/docs/05-deployment.md`, mục 8.

Hai quyền riêng tư hiện được lưu và trả về đúng; tìm bạn và thông báo online sẽ áp dụng ở E2/E3. Hai khóa vận hành ảnh được triển khai sớm ở E1 vì API tải ảnh cần dùng; các phần quản trị còn lại vẫn chờ E7.

Đối chiếu thư viện với nguồn chính thức: [Pillow 13.0.0](https://pypi.org/project/pillow/13.0.0/), [giới hạn giải mã và định dạng đầu vào](https://pillow.readthedocs.io/en/stable/reference/Image.html), [xoay EXIF và cắt ảnh](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html).

## 4. Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Bộ kiểm thử backend hiện có + E1 | **85 passed**, gồm API, ảnh và Socket.IO; chạy trong Docker với PostgreSQL thật |
| Quyền DB | Kiểm thử ứng dụng bằng tài khoản app hạn quyền; migration dùng tài khoản riêng |
| Migration | `upgrade head` → `alembic check` → `downgrade base` → `upgrade head` → `alembic check`: đạt, không lệch model/schema |
| Lint và định dạng | `ruff check backend`, `ruff format --check backend`: đạt |
| Bản Docker | `docker compose build app`: đạt |
| Chạy local | `/ready` trả 200; hợp đồng OpenAPI, sửa hồ sơ, upload và gỡ ảnh qua HTTP thật: đạt |
| Volume và phiên | Tạo lại container `app`: ảnh giữ nguyên nội dung, token đăng nhập vẫn dùng được |
| Bảo toàn dữ liệu | Đối chiếu trước/sau: tài khoản, mật khẩu, trạng thái và cấu hình cũ giữ nguyên; tài khoản thử local đã được dọn |
| Phạm vi bảo vệ | Ảnh hỏng/SVG/GIF, MIME giả, quá dung lượng/pixel, EXIF/metadata, stream quá lớn, ngày sinh sai, khóa ngoài hợp đồng, khách/tài khoản bị khóa, upload bị tắt, cập nhật từng trường, thay/gỡ đồng thời, rollback khi lỗi đĩa và tên khi vào lại phòng: đạt |

Kiểm thử dùng PostgreSQL riêng `videocall_e1_test`, tài khoản app hạn quyền; thao tác downgrade chỉ thực hiện trên DB kiểm thử. Không downgrade dữ liệu của dự án.

Tại thời điểm kết thúc E1, môi trường local đã áp dụng migration `0009`, container `app`, `db`, `sfu` healthy, thay đổi chưa commit/push. Theo yêu cầu kế tiếp, E1 được commit cùng nhánh giai đoạn 2; trạng thái mới nhất xem [báo cáo E2/E3](e2-e3-report.md).

## 5. Cách người dùng nghiệm thu E1

Sau khi chạy bản mới, mở `http://localhost:8000/docs`. Nếu dùng web từ thiết bị khác, thay `localhost` bằng địa chỉ HTTPS đang dùng cho dự án.

1. Dùng `POST /api/v1/auth/login` với tài khoản thành viên hiện có; nên dùng tài khoản thử riêng. Nếu tài khoản đang có phiên khác, xác nhận chuyển thiết bị qua luồng hiện có hoặc đăng xuất trước.
2. Lấy `access_token` từ phản hồi, bấm **Authorize**, nhập token Bearer để thử các API `/me`.
3. GET `/me`, PATCH bằng ví dụ ở mục 2, rồi GET lại để kiểm tra tên, ngày sinh và hai quyền. Thử PATCH riêng một trường để xác nhận các trường khác giữ nguyên.
4. PUT `/me/avatar`, chọn một ảnh JPEG/PNG/WebP. Mở `avatar_url` và `avatar_thumb_url` ở tab trình duyệt mới; hai URL nằm ngoài `/api/v1`.
5. Thay ảnh khác, kiểm tra URL mới; DELETE rồi GET hồ sơ để xác nhận URL trở về `null`.
6. Thử SVG, ảnh hơn 2 MB và ngày sinh tương lai: yêu cầu bị từ chối, dữ liệu hợp lệ trước đó vẫn giữ nguyên.

Giao diện Tài khoản hiện tại chưa có form ngày sinh/quyền riêng tư/upload ở E1. Đây là phần backend sẵn sàng để U6 kết nối sau. Chưa kiểm thử thủ công E1 trên iPhone thực; các luồng gọi qua thiết bị/mạng thật thuộc đợt nghiệm thu riêng.
