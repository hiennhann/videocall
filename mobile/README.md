# Videocall mobile

Ứng dụng React Native kết nối backend Videocall dùng chung với web. Thực hiện các lệnh bên dưới tại thư mục `mobile/`.

## Chuẩn bị kết nối

1. Tạo `.env` từ `.env.example`. Đặt `EXPO_PUBLIC_API_URL` bằng origin HTTPS của máy chủ, gồm cổng nếu có. App tự thêm `/api/v1` khi gọi API. Nếu đang thử qua Wi-Fi, dùng IP LAN hiện tại của laptop chạy Docker.
2. Chạy `npm ci`. Trên điện thoại, kiểm tra rằng địa chỉ máy chủ mở được trước khi đăng nhập app.
3. Với máy chủ LAN dùng CA thử nghiệm, cài CA trên thiết bị. Android debug đọc CA do người dùng cài. Trên iOS, bật tin cậy đầy đủ cho CA và cho phép ứng dụng truy cập mạng nội bộ.

## Android

Máy build cần Android SDK và Java phù hợp. Kết nối điện thoại đã bật USB debugging rồi chạy:

```sh
npm run android -- --device
```

Workflow [Mobile CI](../.github/workflows/mobile.yml) cũng tạo artifact `videocall-android-development`. Tải và giải nén artifact rồi cài `app-debug.apk` lên Android arm64. Bản phát triển kết nối tới Metro chạy trên laptop.

## iPhone

Build cục bộ bằng `npm run ios -- --device` cần macOS và Xcode. Khi phát triển từ Windows, dùng Expo EAS để tạo bản phát triển cài trên iPhone. Cách phân phối này cần tài khoản Expo và Apple Developer trả phí.

```sh
npx eas-cli@latest login
npx eas-cli@latest init
npx eas-cli@latest device:create
npx eas-cli@latest build --platform ios --profile development
```

Lần đầu khởi tạo, EAS liên kết app với dự án Expo của chủ repo. Đăng ký iPhone rồi cài bản phát triển từ đường dẫn EAS trả về. Mở app sau khi bật Developer Mode theo hướng dẫn của iOS. [Hướng dẫn cài bản thử trên iPhone](https://docs.expo.dev/build/internal-distribution/)

Workflow CI tạo thêm artifact `videocall-ios-simulator` để kiểm tra bản native trên trình giả lập của macOS. Artifact này phục vụ máy chạy iOS Simulator.

## Mở app sau khi cài

```sh
npm start
```

`npm run dev` mở cùng máy chủ phát triển. Khi điện thoại và laptop cùng Wi-Fi, dùng QR hoặc liên kết Metro để mở bằng bản phát triển Videocall đã cài. WebRTC dùng module native được biên dịch vào bản phát triển. [React Native WebRTC với Expo](https://react-native-webrtc.github.io/handbook/guides/extra-steps/expo.html)

Dùng hai tài khoản khác nhau để thử gọi web ↔ app. Dùng cùng một tài khoản để thử Hủy hoặc Xác nhận chuyển thiết bị. Kiểm thử nhiều mạng cần địa chỉ HTTPS, TURN và SFU truy cập được từ cả hai mạng. [Tiêu chí nghiệm thu V2](../docs/docs_v2/06-trien-khai.md)
