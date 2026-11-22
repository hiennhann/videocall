# 08 · Tiếp tục phát triển app mobile sau

[Mục lục V2](README.md)

## Quyết định ngày 18/11/2026

Tạm hoãn phát triển và nghiệm thu ứng dụng React Native. Giai đoạn hiện tại tập trung vào web người dùng và web quản trị. Điện thoại dùng trình duyệt để đăng ký, đăng nhập, vào phòng, gọi video và xem livestream.

Mã nguồn trong `mobile/`, cấu hình EAS và workflow mobile được lưu để tiếp tục ở đợt sau. Các luồng API và báo hiệu đã thiết kế cho app được giữ làm tài liệu tham chiếu.

## Trạng thái app đã có

| Phần | Trạng thái |
|---|---|
| Mã ứng dụng | React Native, Expo development build, TypeScript và `react-native-webrtc` trong `mobile/` |
| Tài khoản | Đã viết đăng ký, đăng nhập, lưu refresh token, xác nhận hoặc hủy chuyển thiết bị và đổi mật khẩu bắt buộc |
| Phòng | Đã viết vào phòng theo mã, gọi mesh, bật/tắt mic và camera, nhận thông báo thu hồi phiên và xem livestream từ web |
| Giao diện | Đã viết chế độ sáng/tối và nhận cấu hình tên, màu, phông từ backend |
| Kiểm tra mã | TypeScript và bundle Android/iOS đã đạt |
| Build native | APK Android arm64 và bản iOS Simulator đã biên dịch thành công tại `5901045`; đã kiểm tra các gói tải về |
| Thiết bị thật | Còn cần cài app và xác minh tiếng/hình, quyền camera/mic, kết nối lại và chuyển thiết bị trên Android, iPhone |

Mã và tài liệu đã được push lên `feat/v2-web-dashboard` tại `be59fbe` trước quyết định tạm hoãn. [Kết quả build native](https://github.com/hiennhann/videocall/actions/runs/44219003259) · [Hướng dẫn build mobile](../../mobile/README.md)

## Yêu cầu giữ cho đợt phát triển app

- App Android và iOS dùng chung backend, tài khoản, mã phòng, Socket.IO, TURN và SFU với web. Mã nguồn tiếp tục nằm trong cùng repo.
- Người dùng tạo tài khoản ngay trên app và dùng tài khoản đó trên web. Cấu hình cho phép đăng ký của admin áp dụng ở backend.
- Giữ quy tắc một phiên thiết bị. Xác nhận chuyển sẽ thông báo và đăng xuất thiết bị cũ, rồi cấp phiên cho thiết bị mới. Hủy giữ phiên cũ.
- Áp dụng cấu hình nhận diện, sáng/tối và bảo trì đã thiết kế. Kiểm tra giao diện mobile trên màn hình và bàn phím thật.
- Phạm vi gọi gồm nhập mã phòng, audio/video hai chiều với web và xem livestream phát từ web. Các tính năng mobile mở rộng được xem xét khi hoàn thành các luồng này.

## Khi bắt đầu lại

1. Kiểm tra backend và các hợp đồng API/Socket.IO hiện tại, rồi đối chiếu với mã trong `mobile/`.
2. Cập nhật địa chỉ HTTPS trong `mobile/.env`. Chạy TypeScript và bundle trước khi tạo lại bản cài native.
3. Chuẩn bị Android SDK hoặc dùng APK phát triển từ CI cho Android. Với iPhone, chuẩn bị Mac/Xcode hoặc tài khoản Apple Developer phù hợp cho EAS Build.
4. Cài bản phát triển lên thiết bị thật. Dùng hai tài khoản để thử gọi web ↔ app, sau đó dùng một tài khoản để thử chuyển thiết bị.
5. Thử cùng Wi-Fi trước. Khi có server Internet, tiếp tục Wi-Fi ↔ 4G/5G và xác minh đường TURN, tiếng/hình cùng luồng livestream.

Các artifact trên GitHub có thời hạn lưu 7 ngày. Dùng **Run workflow** trong Mobile CI để tạo bản cài mới khi cần.

## Nghiệm thu web trên điện thoại ở giai đoạn hiện tại

Dùng Safari trên iPhone để mở cùng địa chỉ HTTPS của web Videocall. Khi thử qua Wi-Fi nội bộ, dùng IP LAN hiện tại của laptop chạy Docker và cài chứng chỉ CA thử nghiệm nếu máy chủ đang dùng CA riêng. Cho phép camera và mic khi trình duyệt hỏi.

Dùng hai tài khoản cho laptop và điện thoại để thử cuộc gọi. Thử thêm xem livestream, sáng/tối, bố cục màn hình hẹp, bật/tắt mic/camera và rời phòng. Kết quả được ghi vào [bảng nghiệm thu V2](07-nghiem-thu.md).
