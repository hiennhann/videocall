# 05 · Quy tắc sản phẩm và vận hành

[Mục lục V2](README.md)

## 1. Tài khoản và phân quyền

- Web và app dùng chung bảng tài khoản, quy tắc mật khẩu, giới hạn đăng nhập và trạng thái khóa. Tài khoản đăng ký từ hai giao diện có cùng vai trò mặc định theo V1.
- Máy chủ kiểm tra quyền quản trị trên tuyến `/admin`, API cấu hình và luồng SSE. Phân quyền host và người phát livestream tiếp tục áp dụng tại máy chủ.
- Bản demo cục bộ dùng tài khoản `admin` và mật khẩu `admin123`. Đề xuất khởi tạo qua lệnh demo chạy riêng với giới hạn môi trường dev. Staging và production dùng thông tin quản trị riêng được cấp qua cấu hình bí mật.
- Áp dụng quy ước V1 cho mã HTTP, lỗi Socket.IO, CSRF và audit. Log và audit lưu dấu thời gian, hành động và định danh cần thiết. Loại mật khẩu, refresh token và mã xác nhận chuyển thiết bị khỏi log. [Xác thực và API quản trị V1](../docs/02-api.md)

## 2. Phiên tài khoản

- Một tài khoản người dùng có tối đa một họ phiên đang hoạt động trên web và mobile. Nhiều tab trong cùng hồ sơ trình duyệt dùng cùng phiên, với một quy trình refresh tại mỗi thời điểm. Hồ sơ trình duyệt khác hoặc app chưa có thông tin phiên hợp lệ đi qua quy trình chuyển khi đang có thiết bị khác.
- Backend xác định phiên bằng thông tin xác thực do chính nó cấp. IP và user agent chỉ dùng làm thông tin quan sát. API dùng cookie refresh kiểm tra cùng origin trên các thao tác thay đổi trạng thái. Giới hạn tốc độ cho đăng nhập và xác nhận chuyển.
- Sau xác nhận chuyển, refresh token cũ và access token đã phát hành của họ phiên cũ bị từ chối. Ngắt đúng các socket thuộc họ phiên cũ và dọn trạng thái phòng/SFU theo cơ chế hiện có.
- Mã chuyển thiết bị là mã dùng một lần, hết hạn nhanh và gắn với họ phiên cần thay. Kiểm tra mã và cập nhật phiên trong cùng giao dịch. Mật khẩu sai, mã sai và hủy đều giữ nguyên phiên cũ.
- Phiên quản trị tiếp tục dùng cơ chế riêng tại `/admin`. Khi chuyển thiết bị, backend chỉ xét và thay họ phiên có phạm vi `user`. [Quản lý phiên đồng thời của OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#simultaneous-session-logons)

## 3. Cấu hình giao diện

| Cấu hình | Quy tắc |
|---|---|
| Tên hiển thị | Chuỗi văn bản, cắt khoảng trắng và kiểm tra độ dài. Web và app hiển thị dưới dạng văn bản. |
| Màu chủ đạo | Chọn màu hợp lệ và kiểm tra độ tương phản với chữ trong cả hai chế độ. Đề xuất lưu dưới dạng `#RRGGBB`. |
| Phông chữ | Chọn từ danh sách phông được hỗ trợ trên web và app. Mỗi nền tảng có phông dự phòng. |
| Sáng/tối | Tùy chọn cá nhân lưu trên thiết bị. Cấu hình màu và phông do admin đặt áp dụng trong cả hai chế độ. |

Mở rộng `SettingsSchema` và dùng lại cơ chế lưu/cache/audit của V1. Client đọc các trường công khai từ `/api/v1/config/public`. [Dịch vụ cấu hình V1](../docs/04-settings.md)

## 4. Bảo trì theo chức năng

Đề xuất áp dụng khóa cho thao tác mới. Luồng media đã kết nối tiếp tục. Nếu một người mất kết nối và cần vào lại, yêu cầu mới được kiểm tra theo cấu hình hiện tại. Admin giữ quyền truy cập cấu hình để mở lại tính năng.

| Công tắc | Khi khóa | Điểm kiểm tra |
|---|---|---|
| Đăng ký | Tạm dừng tạo tài khoản từ web và app. | API đăng ký hiện có |
| Gọi nhóm | Tạm dừng tạo và vào phòng gọi nhóm. | API tạo phòng và Socket.IO `join_room` theo loại phòng |
| Livestream | Tạm dừng tạo/vào phòng livestream, bắt đầu phát và đăng ký luồng xem mới. | API tạo phòng, `join_room`, `offer` tới SFU, `subscribe` |
| Chat | Tạm dừng gửi tin nhắn mới. | Sự kiện `chat_message` và thiết lập chat hiện có |
| Chia sẻ màn hình web | Tạm dừng bắt đầu chia sẻ màn hình qua luồng điều khiển hiện có. | Cấu hình media, xử lý sự kiện và điều khiển UI |

Web và app hiển thị lý do bảo trì bằng văn bản. Backend áp dụng kiểm tra kể cả khi client đang giữ cấu hình cũ. Công tắc bảo trì chung V1 tiếp tục có hiệu lực theo quy tắc đã có. [Hiệu lực các thiết lập V1](../docs/04-settings.md#5-hiệu-lực-với-trạng-thái-đang-chạy)

## 5. Hiện diện và Dashboard

- **Phòng đang hoạt động** là phòng có ít nhất một người hiện diện. Phòng trống đang giữ chỗ kết nối lại chỉ tăng bộ đếm khi có người trở lại.
- **Tài khoản đang hoạt động** là tài khoản đăng nhập có kết nối realtime trên web người dùng hoặc app. Tính theo ID duy nhất, kể cả khi mở nhiều tab. Khách có thể làm phòng hoạt động; bộ đếm tài khoản chỉ dùng kết nối của tài khoản đã đăng nhập.
- Dùng kết nối Socket.IO đã xác thực để ghi nhận tài khoản ở lobby và trong phòng. Tab Dashboard quản trị tự nhận số liệu từ một luồng riêng. Đóng kết nối sẽ giảm bộ đếm tài khoản khi đó là kết nối cuối cùng.
- Hai số liệu V2 có ý nghĩa riêng. V1 vẫn cung cấp số kết nối socket và thống kê trạng thái bản ghi phòng cho giám sát. [Luồng cập nhật Dashboard](03-luong-va-hop-dong.md#5-cấu-hình-và-dashboard)
