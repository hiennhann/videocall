# 06 · Triển khai và kiểm thử V2

[Mục lục V2](README.md)

## 1. Thứ tự thực hiện

| Bước | Việc làm | Xong khi |
|---|---|---|
| **V2.0 · Xác nhận bản nền** | Chạy CI/kiểm thử backend và migration V1. Khởi động Compose và thử từ hai laptop thật trên cùng Wi-Fi. Ghi lại commit, bài thử và kết quả. | Hai laptop dùng hai tài khoản gọi được, tiếng/hình hai chiều. Web V1 phát và xem livestream được. |
| **V2.1 · Chuyển thiết bị** | Thực hiện lưu phiên web, mã xác nhận và thu hồi xuyên suốt HTTP, refresh, Socket.IO. Đóng gói thay đổi contract web và backend cùng bước. | Hủy giữ cuộc gọi. Xác nhận buộc phiên cũ thoát và phiên mới vào. Các kiểm thử đồng thời và nhiều tab đều đạt. |
| **V2.2 · Tích hợp mobile** | Tạo `mobile/` bằng React Native và Expo development build. Thử cài Android trước trên máy Windows. Hoàn thành đăng ký, đăng nhập, vào phòng, gọi mesh và xem livestream; sau đó kiểm tra iOS. | Web ↔ Android và web ↔ iOS đạt các bài thử tiếng/hình. Tài khoản đăng ký trên app dùng được trên web. |
| **V2.3 · Cấu hình và sáng/tối** | Tạo cơ chế tài khoản admin demo. Mở rộng settings cho nhận diện và bảo trì. Áp dụng sáng/tối trên web, admin và app. | Thay đổi tên, màu, phông hiện đúng trên web/app; các công tắc khóa và mở lại được; tùy chọn sáng/tối có hiệu lực khi mở lại. |
| **V2.4 · Web và Dashboard** | Áp dụng bố cục hình mẫu cho web người dùng. Làm lại web quản trị với menu và nhận diện riêng. Bổ sung thống kê hiện diện và cập nhật Dashboard. | Duyệt được trên cả màn hình rộng và hẹp. Hai bộ đếm tự cập nhật và đếm đúng khi một tài khoản mở nhiều tab. |
| **V2.5 · Nghiệm thu** | Cài build mobile thử nghiệm, chạy cùng backend staging. Chạy kịch bản hai mạng và ghi kết quả trước khi phát hành. | Có bằng chứng kết nối web ↔ mobile trên Wi-Fi và Wi-Fi ↔ 4G/5G, gồm lượt dùng TURN và một lượt xem livestream. |

Mỗi bước dùng một nhánh tính năng, có tiêu chí kiểm tra và được review trước khi nhập vào `main`. [Quy ước Git V1](../docs/README.md#7-quy-ước-chung-của-dự-án)

## 2. Môi trường chạy

| Môi trường | Thiết lập |
|---|---|
| Máy phát triển | Dùng Compose hiện có cho app, DB, coturn và SFU. Chạy app mobile bằng bản cài phát triển. Nếu thử trên hai thiết bị thật cùng Wi-Fi, dùng IP LAN của host, HTTPS được thiết bị tin cậy và các địa chỉ ICE phù hợp. |
| Staging | Dùng domain HTTPS tin cậy, Caddy chuyển HTTP/WebSocket tới app. TURN công bố địa chỉ relay mà 4G/5G truy cập được. Công bố candidate SFU theo cấu hình mạng của máy chạy SFU. Đặt URL staging trong bản cài mobile thử nghiệm. |
| Production | Dùng thông tin quản trị riêng, TLS tin cậy, cấu hình firewall và sao lưu DB theo giai đoạn B. Cổng HTTP điều khiển SFU và PostgreSQL dành cho kết nối nội bộ. |

Ở LAN dùng CA thử nghiệm, cấu hình tin cậy cho bản debug của app nếu cần. Android có thể cần khai báo CA trong cấu hình mạng của app. Staging dùng CA công cộng được hệ điều hành tin cậy. Đối chiếu các cổng TURN và SFU với cấu hình Compose thực tế; giới hạn của dev và cấu hình giai đoạn B có thể khác nhau. [Mạng và cổng V1](../docs/05-deployment.md#3-cổng-cần-mở-firewall) · [Cấu hình mạng Android](https://developer.android.com/privacy-and-security/security-config)

## 3. Ma trận kiểm thử

| Luồng | Các trường hợp cần chạy |
|---|---|
| Migration | Nâng cấp DB V1 có tài khoản, phòng, tin nhắn và settings. Đối chiếu dữ liệu trước và sau. Xác nhận hành vi phiên cũ theo kế hoạch chuyển V1. |
| Tài khoản | Đăng ký trên app rồi đăng nhập web; đăng ký bị khóa; thông tin sai; đăng nhập nhiều tab trong một phiên; xác nhận/hủy khi đang gọi; xác nhận trùng hoặc hết hạn; HTTP, refresh và socket của máy cũ sau chuyển. |
| Gọi nhóm | Hai laptop; web ↔ Android; web ↔ iOS; hai chiều audio/video; vào phòng có mật khẩu; bật/tắt media; rời phòng; đường trực tiếp và lượt buộc TURN; giới hạn bốn người theo V1. |
| Livestream | Host phát từ web; app nhận âm thanh và giải mã video; đổi hoặc dừng người phát; vào sau khi phòng đã phát; giới hạn bốn người xem theo V1. |
| Quản trị | Kiểm tra phân quyền và hai giao diện quản trị/người dùng; tạo tài khoản demo cục bộ; đổi tên, màu, phông; khóa/mở chức năng từ admin; client giữ cấu hình cũ vẫn chịu kiểm tra từ máy chủ. |
| Dashboard | Phòng từ trống sang có người và trở lại trống; tài khoản nhiều tab; khách vào phòng; reconnect cửa sổ admin; người dùng thường bị từ chối khi mở luồng cập nhật. |
| Giao diện | Sáng/tối lưu được; trang hẹp có thể thu gọn thanh bên; thao tác được khi lỗi kết nối hoặc đang bảo trì. |

Ghi phiên bản app, trình duyệt và hệ điều hành, hai mạng sử dụng, loại ICE đã chọn và kết quả tiếng/hình. Khi cần kiểm chứng media, xem gói audio nhận được và số khung video giải mã hoặc đối chiếu trực tiếp trên thiết bị.

## 4. Phát hành và quay về bản trước

1. Trên CI, chạy kiểm thử backend và migration PostgreSQL trước. Chạy kiểm tra kiểu mã, build thử mobile và kiểm tra web khi các thành phần đó có thay đổi.
2. Sao lưu DB trước migration. Ghi lại commit, image, cấu hình và bản cài mobile của bản ổn định gần nhất.
3. Khi deploy staging, nâng cấp schema, kiểm tra `/ready`, rồi kiểm tra đăng nhập, chuyển thiết bị, truy cập quản trị, WSS, ICE và Dashboard. Kiểm tra Prometheus và log theo `X-Request-ID`.
4. Giữ backend và client web cùng phiên bản hợp đồng đăng nhập. Phát bản mobile thử tương thích; kiểm tra lại các luồng chính sau khi cập nhật.
5. Nếu cần quay về bản trước, phục hồi cặp backend/web tương thích và kiểm tra schema trước khi đưa vào phục vụ. Chỉ chạy kế hoạch phục hồi DB đã thử trên bản sao. Kiểm tra khả năng đăng nhập lại và các phiên sau khi phục hồi. [Backup và rollback V1](../docs/05-deployment.md)
