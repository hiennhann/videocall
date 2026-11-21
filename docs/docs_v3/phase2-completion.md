# Nghiệm thu giai đoạn 2 V3

Giai đoạn 2 trên nhánh `feat/phase2` gồm hồ sơ và ảnh đại diện E1, bạn bè E2, realtime E3, lời mời gọi E5, lịch sử cuộc gọi E6, tin nhắn riêng E4 và phần quản trị E7.

| Bước | Phần đã hoàn tất |
|---|---|
| E5 · migration `0011` | Mời bạn từ phòng đang tham gia, hộp thư lời mời kể cả khi offline, từ chối, hủy, hết hạn, vào phòng riêng bằng lời mời đúng người và đúng phòng. Vẫn áp dụng giới hạn chỗ và lệnh cấm. |
| E6 · migration `0012` | Ghi mốc vào/ra bằng hàng đợi nền, đóng lượt treo khi khởi động, lọc lịch sử, tải chat phòng và xóa liên kết lịch sử của chính mình. |
| E4 · migration `0013` | Chat một đối một qua Socket.IO, thử gửi lại cùng ID chỉ lưu một lần, con trỏ trước/sau, đánh dấu đã đọc, báo đang gõ và xóa mềm. |
| E7 | Chi tiết hồ sơ và số liệu hoạt động, gỡ avatar có audit, danh sách/chi tiết phòng đã kết thúc, số liệu dashboard và chính sách vận hành. |

Các bước kiểm tra dưới đây dùng Swagger tại [localhost:8000/docs](http://localhost:8000/docs) và Socket.IO của dự án. Giao diện người dùng cho bạn bè, tin nhắn, lời mời và lịch sử thuộc U5/U6.

1. Đăng nhập hai tài khoản và kết bạn. Mở một phòng riêng và vào phòng bằng tài khoản A. Gọi `POST /api/v1/rooms/{code}/invites` với `{"user_ids":["<ID B>"]}`, rồi kiểm tra hộp thư của B qua `GET /api/v1/invites`.
2. Kết nối socket của B và gửi `join_room` với `{"code":"<mã phòng>","invite_id":"<ID lời mời>"}`. Thử bằng tài khoản thứ ba, với lời mời đã dùng và với lời mời hết hạn để kiểm chứng quyền vào phòng.
3. Gửi một tin chat phòng, rời rồi vào lại. Kiểm tra `GET /api/v1/me/call-history/{code}` và tải `/chat-export`. Từ tài khoản chưa tham gia, yêu cầu tải trả 404. Người có lời mời lỡ chỉ thấy thông tin lời mời, không có người tham gia hay nội dung chat.
4. Gửi `dm_send` với `to_user_id`, `text`, `client_msg_id`. Gửi lại cùng ID để kiểm tra cùng ACK và không lặp thông báo. Dùng `dm_read` hoặc API mark read sau khi đọc. Khi hủy kết bạn hoặc chặn, lịch sử cũ chuyển sang chỉ đọc; người gửi vẫn có thể xóa mềm tin của mình.
5. Đăng nhập admin, mở `GET /api/v1/admin/dashboard`, `/admin/users/{id}` và `/admin/call-history`. Thử gỡ avatar và tra `user.avatar_remove` trong audit. Quyền đọc DM chỉ dành cho hai người trong cuộc.

Khi web kết nối lại, nó lấy lại danh sách bạn, lời mời kết bạn, lời mời gọi và cuộc trò chuyện qua HTTP. Với cuộc trò chuyện tab đã có con trỏ, nó lấy thêm những tin bỏ lỡ qua `after` và phát snapshot `videocall:communications-synced` cho lớp giao diện. Người dùng mất kết nối lâu vẫn có thể lấy lịch sử đầy đủ bằng các API theo con trỏ.

Chính sách mặc định giữ chat phòng 30 ngày, lịch sử cuộc gọi 90 ngày và DM vô thời hạn. Công việc nền dọn phòng đóng sau cả hai ngưỡng chat và lịch sử. Hàng đợi lịch sử giữ tối đa 4096 thao tác. Lỗi lưu DB hoặc hàng đợi đầy được ghi log, và tiến trình dừng đột ngột có thể làm mất những thao tác chưa ghi. Lượt đã lưu mà còn mở sẽ được đóng khi app khởi động lại. Dashboard tính số cuộc gọi và phút gọi theo ngày UTC, mỗi phòng tính một lần.
