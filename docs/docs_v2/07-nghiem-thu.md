# 07 · Theo dõi nghiệm thu V2

[Mục lục V2](README.md)

## Môi trường ngày 18/11/2026

Máy phát triển dùng Windows và Docker Desktop. Người dùng có iPhone, hiện chưa có Mac, Apple Developer trả phí hoặc VPS/domain. Theo quyết định ngày 18/11/2026, nghiệm thu điện thoại dùng Safari. App React Native được lưu để phát triển sau. [Kế hoạch app](08-app-mobile-sau-nay.md)

## Bằng chứng đã có

| Phần | Kết quả |
|---|---|
| Backend tại `77cee0c` | 44 bài kiểm thử đạt. Backend CI trên GitHub thành công. [Lượt chạy](https://github.com/hiennhann/videocall/actions/runs/44116578659) |
| Phiên thiết bị | Đã thử hai hồ sơ Chrome và nhiều tab. Hủy giữ phiên cũ. Xác nhận chuyển làm cả hai tab cũ thoát, mở lobby ở hồ sơ mới. |
| WebRTC trên web | Hai phiên Chrome trên một laptop nhận gói audio và giải mã khung video trong cuộc gọi 1–1 và livestream. |
| Quản trị và giao diện | Đã đăng nhập tài khoản demo, nhận số liệu Dashboard qua SSE, kiểm tra bố cục hẹp và lưu chế độ sáng/tối. |
| Mobile tại `77cee0c` | TypeScript và bundle Android/iOS đạt trên Mobile CI. [Lượt chạy](https://github.com/hiennhann/videocall/actions/runs/44116578931) |

## Build native đã lưu cho đợt app sau

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
| Laptop ↔ web trên iPhone | Safari và laptop cùng Wi-Fi, HTTPS được điện thoại tin cậy | Đăng ký/đăng nhập, vào phòng, tiếng/hình hai chiều và xem livestream từ laptop |
| Hai laptop thật | Hai tài khoản khác nhau, hai máy cùng Wi-Fi và HTTPS tin cậy | Vào cùng mã phòng, nhận tiếng/hình, bật/tắt media và rời phòng |
| Wi-Fi ↔ 4G/5G | Backend HTTPS cùng TURN/SFU có địa chỉ truy cập được từ cả hai mạng | Kết nối được trong cả lượt dùng đường trực tiếp phù hợp và lượt buộc TURN |

Với từng lượt chạy, ghi commit, trình duyệt, hệ điều hành, mạng sử dụng, loại candidate ICE, kết quả tiếng/hình và lỗi quan sát được. Dùng tài khoản riêng trên mỗi thiết bị khi thử gọi, rồi dùng chung tài khoản cho bài thử chuyển thiết bị. Các bài thử web ↔ app Android/iPhone tiếp tục theo tài liệu phát triển app sau.
