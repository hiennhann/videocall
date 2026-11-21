# Nghiệm thu U2 và U3

Nhánh `feat/ui_v3` kế thừa giai đoạn 2 và bộ nhận diện Videocall. Trang chủ, Phòng của tôi, Tài khoản, Vào phòng và Tạo phòng giữ điều hướng tải từng trang. Tin nhắn trong phòng và Thành viên là các tab trong cuộc gọi.

| Bước | Đã triển khai |
|---|---|
| U2 · Trang xác thực | Tab Đăng nhập/Đăng ký, tên khách theo cấu hình, hướng dẫn độ dài và ước tính độ mạnh mật khẩu, lỗi ngay dưới trường khi máy chủ có lỗi theo trường. |
| U2 · Trang chủ | Phòng đang mở, lời mời đến, số tin nhắn chưa đọc, năm cuộc gọi gần đây, chi tiết và tải chat khi còn lưu. |
| U2 · Phòng của tôi | Mã phòng, loại phòng, số người, trạng thái mật khẩu, vào phòng, sao chép mã và đóng phòng có xác nhận. Biểu mẫu Tạo phòng cho chọn giới hạn người của cuộc gọi nhóm. |
| U3 · Chuẩn bị vào phòng | Kiểm tra camera và mic theo yêu cầu, mức mic, tắt/bật từng thiết bị trước khi vào, chọn đầu vào và chọn loa nếu trình duyệt hỗ trợ. |
| U3 · Cuộc gọi | Lưới video co theo số người, màn hình chia sẻ ở vùng chính, viền người đang nói từ thống kê audio, đồng hồ, số liệu RTT/mất gói/bitrate/đường ICE và sao chép báo cáo. |
| U3 · Nội dung phòng | Chat, Thành viên và Mời. Host có thể mời người khác ra. Trên màn hình hẹp, nội dung phòng mở bằng ngăn kéo ở đáy và đóng bằng Escape. |

## Thử trên máy

Mở Docker Desktop và chạy `docker compose up -d --build --wait` ở thư mục dự án. Sau đó mở [Videocall](http://localhost:8000/).

1. Thử chuyển tab Đăng nhập/Đăng ký bằng chuột và phím mũi tên. Nhập mật khẩu ngắn rồi nhập dài hơn để xem chỉ báo. Vào bằng tên khách và thử nhập mã phòng từ trang riêng.
2. Đăng nhập tài khoản thành viên, tạo phòng riêng và kiểm tra camera/mic. Tắt mic trước khi bấm **Vào phòng**. Trong cuộc gọi, nút mic vẫn ở trạng thái tắt.
3. Dùng tài khoản bạn bè thứ hai. Trong tab **Mời**, chọn người đó và gửi. Trên Trang chủ của họ, bấm **Tham gia** ở thẻ lời mời để vào đúng phòng.
4. Mở **Chỉ số mạng** khi đã kết nối với người thứ hai, kiểm tra số liệu và thử sao chép. Thu nhỏ cửa sổ, mở ngăn kéo **Nội dung phòng**, chuyển tab rồi đóng bằng Escape.
5. Gửi một tin chat rồi rời phòng. Trên Trang chủ, mở **Chi tiết** lịch sử và thử tải nhật ký chat. Trong **Phòng của tôi**, thử hủy xác nhận đóng phòng rồi thực hiện đóng.

Camera/mic vật lý, chọn loa trên thiết bị thật và Safari iPhone cần được kiểm tra trực tiếp khi có thiết bị. Kiểm tra tự động dùng Canvas và Web Audio làm nguồn media, truyền qua kết nối WebRTC và SFU của bản thử.

## Kết quả kiểm tra

- **144 lượt kiểm tra bố cục** trên Chrome và Edge, ở 1440, 900 và 390 px, cả sáng và tối. Không ghi nhận tràn ngang trang, lỗi JavaScript hoặc CSP. [Kết quả tự động](assets/u2-u3/checks.json)
- Hai trình duyệt qua các luồng đăng ký, đăng nhập, khách, điều hướng giữa các tài liệu riêng, xem trước và giữ lựa chọn mic, gọi nhóm hai chiều, xem livestream, mời bạn vào phòng riêng, đóng ngăn kéo bằng Escape, mở chi tiết lịch sử và xác nhận đóng phòng.
- **117 kiểm thử backend** qua PostgreSQL và Socket.IO thật. Kiểm tra migration tới `0013`, nâng/hạ trên database thử nghiệm, Ruff và cú pháp JavaScript đều đạt.

## Ảnh từ bản thử

| Màn hình | Ảnh |
|---|---|
| Đăng nhập | [Desktop, sáng](assets/u2-u3/login-desktop-light.png) |
| Trang chủ với phòng và lịch sử thật | [Desktop, sáng](assets/u2-u3/home-desktop-light.png) |
| Xem trước camera và thiết bị | [Điện thoại, sáng](assets/u2-u3/preview-phone-light.png) |
| Cuộc gọi, tab Mời và số liệu mạng | [Desktop, tối](assets/u2-u3/room-desktop-dark.png) |
