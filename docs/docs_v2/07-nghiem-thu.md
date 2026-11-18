# 07 · Theo dõi nghiệm thu V2

[Mục lục V2](README.md)

## Môi trường ngày 18/11/2026

Máy phát triển dùng Windows và Docker Desktop. Người dùng có iPhone, hiện chưa có Mac, Apple Developer trả phí hoặc VPS/domain. Các bài thử cần iPhone thật và hai mạng Internet được thực hiện khi có bản cài phù hợp và server truy cập được.

## Bằng chứng đã có

| Phần | Kết quả |
|---|---|
| Backend tại `77cee0c` | 44 bài kiểm thử đạt. Backend CI trên GitHub thành công. [Lượt chạy](https://github.com/hiennhann/videocall/actions/runs/44116578659) |
| Phiên thiết bị | Đã thử hai hồ sơ Chrome và nhiều tab. Hủy giữ phiên cũ. Xác nhận chuyển làm cả hai tab cũ thoát, mở lobby ở hồ sơ mới. |
| WebRTC trên web | Hai phiên Chrome trên một laptop nhận gói audio và giải mã khung video trong cuộc gọi 1–1 và livestream. |
| Quản trị và giao diện | Đã đăng nhập tài khoản demo, nhận số liệu Dashboard qua SSE, kiểm tra bố cục hẹp và lưu chế độ sáng/tối. |
| Mobile tại `77cee0c` | TypeScript và bundle Android/iOS đạt trên Mobile CI. [Lượt chạy](https://github.com/hiennhann/videocall/actions/runs/44116578931) |

## Build native

Theo dõi bước biên dịch Android và iOS tại commit `5901045` trên [lượt chạy native](https://github.com/hiennhann/videocall/actions/runs/44219003259). [Workflow](../../.github/workflows/mobile.yml)

| Nền tảng | Kết quả |
|---|---|
| iOS Simulator | Biên dịch Release thành công. Đã tải artifact và kiểm tra binary cùng `CFBundleIdentifier=com.hiennhann.videocall`, nền tảng `iPhoneSimulator`. |
| Android | Biên dịch APK phát triển thành công cho arm64. Đã tải gói, kiểm tra định danh `com.hiennhann.videocall` và thư viện `lib/arm64-v8a/libjingle_peerconnection_so.so`. |

Cấu hình EAS có profile `development` cho thiết bị thật và `simulator` cho iOS Simulator. Lệnh `npm run dev` được bổ sung để mở máy chủ Metro tương tự `npm start`. [Cài và chạy mobile](../../mobile/README.md)

Backend CI tại cùng commit cũng thành công. Các artifact native được giữ trên GitHub trong 7 ngày và có thể tạo lại bằng workflow. [Backend CI](https://github.com/hiennhann/videocall/actions/runs/44219003260)

## Các bài thử cần thiết bị và hạ tầng

| Bài thử | Điều kiện | Tiêu chí |
|---|---|---|
| Web ↔ app Android | Điện thoại Android arm64, bản phát triển đã cài và backend cùng Wi-Fi | Đăng ký/đăng nhập, vào phòng, tiếng/hình hai chiều và xem livestream web |
| Web ↔ app iPhone | Mac với Xcode để cài bằng tài khoản Apple hoặc tài khoản Apple Developer cho EAS Build; iPhone đã đăng ký | Các luồng tài khoản, chuyển thiết bị, tiếng/hình hai chiều và xem livestream |
| Hai laptop thật | Hai tài khoản khác nhau, hai máy cùng Wi-Fi và HTTPS tin cậy | Vào cùng mã phòng, nhận tiếng/hình, bật/tắt media và rời phòng |
| Wi-Fi ↔ 4G/5G | Backend HTTPS cùng TURN/SFU có địa chỉ truy cập được từ cả hai mạng | Kết nối được trong cả lượt dùng đường trực tiếp phù hợp và lượt buộc TURN |

Với từng lượt chạy, ghi commit, phiên bản bản cài, hệ điều hành, mạng sử dụng, loại candidate ICE, kết quả tiếng/hình và lỗi quan sát được. Dùng tài khoản riêng trên mỗi thiết bị khi thử gọi, rồi dùng chung tài khoản cho bài thử chuyển thiết bị.
