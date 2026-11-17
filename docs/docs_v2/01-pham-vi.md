# 01 · Phạm vi và nghiệm thu V2

[Mục lục V2](README.md)

## 1. Yêu cầu đã chốt

| Hạng mục | Phạm vi | Đạt khi |
|---|---|---|
| Một dự án | Web người dùng, web quản trị và React Native cùng repo. Web và app dùng chung backend, tài khoản và mã phòng. | Tài khoản đăng ký trên app đăng nhập được trên web. Cả hai vào cùng một phòng theo mã. |
| Mobile Android và iOS | Đăng ký, đăng nhập, vào phòng, bật/tắt mic và camera, gọi video và xem livestream phát từ web. | Có cuộc gọi web ↔ mobile với tiếng và hình hai chiều. App xem được âm thanh và hình ảnh từ livestream web. Kiểm tra trên cả Android và iOS trước nghiệm thu. |
| Giao diện web người dùng | Thiết kế lại theo hình mẫu. Giữ các luồng V1 gồm đăng nhập, lobby, gọi nhóm, livestream và các điều khiển hiện có. | Tạo/vào phòng và điều khiển cuộc gọi được trên máy tính và màn hình hẹp. [Hình mẫu](../docs/assets/v2-web-layout.png) |
| Giao diện web quản trị | Trang `/admin` có bố cục cùng hướng thiết kế, bảng màu và menu riêng. Dashboard có số phòng đang hoạt động và số tài khoản đang hoạt động theo thời gian thực. | Hai chỉ số thay đổi tại chỗ theo hiện diện. Mở nhiều tab trong cùng phiên chỉ tính một tài khoản. |
| Sáng và tối | Web người dùng, web quản trị và app đều có lựa chọn Sáng/Tối. | Tùy chọn được lưu trên thiết bị và áp dụng lại khi mở lần sau. |
| Một thiết bị mỗi tài khoản người dùng | Sau khi xác thực hợp lệ trên thiết bị mới, người dùng chọn chuyển thiết bị hoặc hủy. Xác nhận sẽ thông báo, đăng xuất máy cũ và cấp phiên cho máy mới. Hủy giữ phiên máy cũ. | Xác nhận làm mất quyền HTTP, refresh và Socket.IO của phiên cũ. Hủy để cuộc gọi trên máy cũ tiếp tục. Hai lượt xác nhận đồng thời chỉ để lại một phiên hợp lệ. |
| Tài khoản quản trị demo | Bản demo cục bộ có thông tin đăng nhập cố định `admin` / `admin123` tại `/admin`. Môi trường có người dùng thật dùng mật khẩu riêng. | Demo đăng nhập được. Bản staging và production yêu cầu cấu hình tài khoản quản trị riêng. |
| Cấu hình từ quản trị | Tên hiển thị dự án, màu chủ đạo, phông chữ và khóa/mở từng chức năng để bảo trì. | Web và app đọc cùng cấu hình. API và Socket.IO áp dụng trạng thái bảo trì. Quản trị viên mở lại được tính năng từ `/admin`. |

## 2. Giới hạn phát hành đề xuất

- Gọi nhóm tiếp tục dùng mesh, tối đa 4 người theo V1. Livestream tiếp tục dùng SFU với một người phát và tối đa 4 người xem. Người phát trong luồng nghiệm thu V2 dùng web.
- Bắt đầu với Android trên máy Windows đang dùng, sau đó nghiệm thu iOS bằng bản cài thử trên thiết bị thật.
- Để dành cho đợt sau các tính năng phát livestream từ app, chia sẻ màn hình native, cuộc gọi nền, thông báo đẩy, phát hành qua cửa hàng và mở rộng nhiều máy chủ. Các chức năng web đã có ở V1 tiếp tục được kiểm thử hồi quy.
- Phạm vi giao diện mobile tập trung vào các luồng trong bảng trên. Cách trình bày lịch sử chat và chỉ số mạng của app có thể xem lại khi hoàn thành luồng gọi chính.

## 3. Nghiệm thu theo môi trường

| Môi trường | Bài thử |
|---|---|
| Máy phát triển | Kiểm thử backend, trình duyệt, dữ liệu V1 sau migration và Docker. |
| Wi-Fi nội bộ | Hai laptop thật xác nhận bản nền. Laptop ↔ điện thoại thật xác nhận gọi video và livestream V2. |
| Staging truy cập từ Internet | Laptop dùng Wi-Fi và điện thoại dùng 4G/5G thử vào cùng mã phòng. Xác nhận HTTPS, Socket.IO, tiếng/hình và đường relay TURN bằng số liệu kết nối. |

Để thử gọi giữa hai thiết bị, dùng hai tài khoản mẫu khác nhau. Bài thử chuyển thiết bị dùng cùng một tài khoản.
