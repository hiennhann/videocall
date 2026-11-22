# Nghiệm thu giao diện U4–U7

Giao diện Videocall trên nhánh `feat/ui_v3` dùng các API giai đoạn 2 và migration `0013`.

| Bước | Phạm vi triển khai |
|---|---|
| U4 | `/admin` giữ số phòng hoạt động và số tài khoản trực tuyến cập nhật tức thời. Tổng quan và danh sách phòng làm mới qua HTMX mỗi 5 giây. Quản trị viên có thể lọc phòng theo tên, mã, chủ trì và loại phòng, xem người tham gia, mời ra và đóng phòng. Trang tài khoản hiển thị avatar và thông tin hoạt động. Trang cấu hình chia theo nhóm và xác nhận trước khi áp dụng thay đổi. |
| U5 | `/friends` tìm tài khoản theo email đầy đủ và quản lý lời mời, kết bạn, chặn. `/messages` hỗ trợ nhắn riêng, đang nhập, đã xem, xóa tin của mình và đồng bộ khi nối lại. Lời mời gọi hiện trong chuông thông báo và thẻ có đếm ngược. Tab Mời trong phòng cho tìm và chọn bạn bè. |
| U6 | `/account` có hồ sơ, avatar, ngày sinh, bảo mật, quyền riêng tư và giao diện. `/history` có bộ lọc, chi tiết, tải chat và xác nhận xóa. `/admin/reports` dựng biểu đồ 7 ngày trên máy chủ, xuất CSV và mở chi tiết cuộc gọi. Ngày và giờ của báo cáo dùng UTC. |
| U7 | Web người dùng dùng thanh điều hướng đáy ở chiều rộng điện thoại. Các trang hỗ trợ phím Tab, phím mũi tên ở nhóm tab, Escape trong hộp thoại và ngăn kéo, cùng thông báo trạng thái đọc được qua công nghệ hỗ trợ. |

Dashboard truy vấn Prometheus khi có `PROMETHEUS_URL`, và hiển thị `—` khi thiếu chuỗi số liệu. Băng thông TURN là ước tính từ các phiên coturn đã kết thúc trong cửa sổ 5 phút. `TURN_CAPACITY_MBPS` là ngưỡng tham chiếu tùy chọn. Tỷ lệ vào phòng trong 24 giờ lấy lượt vào thành công chia cho tổng lượt xử lý `join_room`. Báo cáo lấy số tài khoản và cuộc gọi từ PostgreSQL. [Định dạng API Prometheus](https://prometheus.io/docs/prometheus/latest/querying/api/) · [Bộ đếm coturn](https://github.com/coturn/coturn/blob/master/src/apps/relay/prom_server.c)

Các phép thử sử dụng camera và mic mô phỏng trong Chrome và Edge. Safari trên iPhone và thiết bị thật cần nghiệm thu riêng.

## Kết quả kiểm tra

Backend vượt qua 117 kiểm thử với PostgreSQL và Socket.IO. Alembic nâng đến `0013`, hạ về base, nâng lại và xác nhận schema khớp model. Ruff và kiểm tra cú pháp JavaScript đều đạt.

Chrome và Edge vượt qua **96 lượt kiểm tra bố cục** ở 1440, 900 và 390 px, cả sáng và tối. Hai trình duyệt đã chạy qua luồng đăng nhập, kết bạn, nhắn tin, xem lại tin sau khi mất kết nối, nhận lời mời gọi, tải chat, chỉnh hồ sơ và avatar, làm mới dashboard qua HTMX, đóng phòng và xem chi tiết báo cáo. Bộ chạy ghi nhận 0 lỗi JavaScript hoặc CSP. [Kết quả hai trình duyệt](assets/u4-u7/checks.json)

Lighthouse 13.6.0 đo hạng mục Accessibility trên Chrome với cấu hình mobile. Cả tám trang đã đăng nhập đạt **100/100** trên lượt đo. [Kết quả Lighthouse theo URL](assets/u4-u7/lighthouse.json)

## Ảnh từ môi trường thử nghiệm

| Web người dùng | Web quản trị |
|---|---|
| [Bạn bè trên tablet](assets/u4-u7/friends-tablet-light.png) | [Tổng quan trên desktop](assets/u4-u7/dashboard-desktop-dark.png) |
| [Tin nhắn trên điện thoại](assets/u4-u7/messages-phone-light.png) | [Báo cáo trên desktop](assets/u4-u7/reports-desktop-dark.png) |
| [Lịch sử trên điện thoại](assets/u4-u7/history-phone-light.png) | |
| [Hồ sơ trên desktop](assets/u4-u7/account-desktop-light.png) | |

## Cách chạy lại kiểm tra

1. Dùng database phát triển riêng và tạo tài khoản quản trị thử bằng `python -m app.cli create-demo-admin`. Đặt `UI_BASE_URL` nếu ứng dụng thử dùng địa chỉ khác `http://localhost:18024`.
2. Cài Playwright vào `.lan/u1-tools` và Lighthouse 13.6.0 vào `.lan/ui-final-tools`. Chạy `node tools/check-ui-v3-final.cjs` với Chrome và Edge đã cài trên Windows. Ảnh và danh sách điểm kiểm tra lưu ở `.lan/ui-final-views`.
3. Chạy `node tools/check-ui-lighthouse.cjs` để đo Accessibility bằng cấu hình mobile của Lighthouse. Hai lệnh tạo tài khoản thử nên dùng cùng lượt chạy trên một môi trường riêng đã khởi động mới để nằm trong hạn mức đăng ký mặc định.
