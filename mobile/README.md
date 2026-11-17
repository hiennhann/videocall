# Videocall mobile

Ứng dụng React Native kết nối backend Videocall dùng chung với web.

1. Tạo `.env` từ `.env.example` trong thư mục `mobile`. Đặt `EXPO_PUBLIC_API_URL` bằng địa chỉ HTTPS mà thiết bị truy cập được.
2. Chạy `npm ci`. Chạy `npm run android -- --device` với Android SDK hoặc `npm run ios -- --device` với Xcode để tạo bản cài phát triển.
3. Chạy `npm start` và mở bản cài phát triển. Dùng một tài khoản khác với tài khoản đang dùng trên web khi thử gọi giữa hai thiết bị.

Với máy chủ LAN dùng chứng chỉ riêng, cài chứng chỉ CA trên thiết bị. Bản Android debug đọc CA do người dùng cài. Trên iOS, bật tin cậy đầy đủ cho CA thử nghiệm. Kiểm thử nhiều mạng bằng địa chỉ HTTPS/TURN/SFU truy cập được từ cả hai mạng. [Tài liệu V2](../docs/docs_v2/06-trien-khai.md)
