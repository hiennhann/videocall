# Videocall V2

**Trạng thái** · Bản thiết kế để review.

**Bản nền** · A1–A11 trên `main` tại commit `de9d1b4`. V1 có web gọi video, trang quản trị, API FastAPI, PostgreSQL, Socket.IO, TURN, SFU và chỉ số Prometheus. Lộ trình triển khai hạ tầng giai đoạn B được mô tả trong tài liệu V1. [Tài liệu thiết kế V1](../docs/README.md) · [Triển khai V1](../docs/05-deployment.md)

## Tài liệu
| File | Nội dung |
|---|---|
| [01-pham-vi.md](01-pham-vi.md) | Yêu cầu đã chốt, giới hạn V2 và tiêu chí nghiệm thu |
| [02-kien-truc.md](02-kien-truc.md) | Kiến trúc, công nghệ, các phần dùng lại từ V1 và thay đổi dữ liệu |
| [03-luong-va-hop-dong.md](03-luong-va-hop-dong.md) | Đăng ký, chuyển thiết bị, vào phòng, livestream và cập nhật Dashboard |
| [04-giao-dien.md](04-giao-dien.md) | Bố cục theo hình mẫu, web quản trị riêng, màn hình mobile và chế độ sáng/tối |
| [05-quy-tac.md](05-quy-tac.md) | Phân quyền, thông tin đăng nhập, cấu hình, bảo trì và cách đếm hiện diện |
| [06-trien-khai.md](06-trien-khai.md) | Thứ tự thực hiện, môi trường chạy, kiểm thử và quay về bản trước |
| [07-nghiem-thu.md](07-nghiem-thu.md) | Kết quả đã xác minh và điều kiện chạy các bài thử còn lại |

## Đọc trước khi triển khai

1. Review [phạm vi và tiêu chí nghiệm thu](01-pham-vi.md) để chốt đầu ra.
2. Review [luồng chuyển thiết bị](03-luong-va-hop-dong.md#2-chuyển-thiết-bị) và [quy tắc bảo trì](05-quy-tac.md#4-bảo-trì-theo-chức-năng) vì chúng ảnh hưởng trực tiếp đến người đang gọi.
3. Dùng [lộ trình](06-trien-khai.md#1-thứ-tự-thực-hiện) để chọn bước đầu. Các tên trường API mới, kỹ thuật lưu phiên web và cách cập nhật Dashboard trong bộ tài liệu này là **thiết kế đề xuất** để review.

Luồng gọi V1 đã được kiểm thử bằng các phiên trình duyệt trên một laptop. Kiểm thử trên thiết bị thật và giữa Wi-Fi với 4G/5G được đưa vào kế hoạch nghiệm thu V2.
