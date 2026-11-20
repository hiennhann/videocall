# E2/E3 — Bạn bè và realtime theo tài khoản

Ngày: 20/11/2026. Nhánh: `feat/phase2`.

Phạm vi được yêu cầu: triển khai E2 và E3 của giai đoạn 2, kiểm thử rồi push nhánh này. Nhánh kế thừa UI V3 hiện tại và E1 (commit nền `e0ce967`). E4/E5/E6/E7 và màn hình Bạn bè/Tin nhắn U5 chưa triển khai trong đợt này; không merge vào main.

## 1. Các phần đã triển khai

| Phần | Tệp chính | Kết quả |
|---|---|---|
| Dữ liệu E2 | `models/friend.py`, `migrations/versions/0010_create_friends.py` | Ba bảng friend_requests/friendships/user_blocks; FK CASCADE, ràng buộc không tự mời/chặn, cặp bạn bè chuẩn hóa a < b, unique lời mời pending; app có quyền DB cần thiết |
| Hợp đồng HTTP | `schemas/friends.py`, `api/friends.py` | Tìm email chính xác, lời mời hai chiều, chấp nhận/từ chối/hủy, danh sách bạn phân trang, hủy bạn, chặn/bỏ chặn |
| Nghiệp vụ | `services/friend_service.py` | Kiểm tra quyền ở service, khóa hai dòng user theo thứ tự UUID, hạn mức, TTL, cooldown, che từ chối, tự chấp nhận lời mời ngược |
| Realtime E3 | `services/friend_events.py`, `realtime/friends.py`, `realtime/server.py` | Room user riêng, năm sự kiện bạn bè/hồ sơ/online, cache, chờ offline 5 giây, dọn timer khi shutdown |
| Hồ sơ và tài khoản | `api/me.py`, `services/account_events.py`, `services/admin_service.py` | Đổi tên/ảnh cập nhật cho bạn bè; đổi quyền online xóa trạng thái cũ; khóa/thu hồi phiên tiếp tục dùng vòng đời tài khoản hiện có |
| Cấu hình | `schemas/settings.py` | Năm khóa bạn bè; mặc định 200 bạn, 50 lời mời, TTL 30 ngày; hai cờ public |
| Đồng bộ web | `client/js/friends-sync.js`, `workspace.js`, `room.js` | Tự lấy snapshot bạn bè/lời mời khi kết nối lại; dùng kết nối có sẵn, không thêm màn hình mới |
| Kiểm thử | `tests/integration/test_friends.py`, `test_rooms_socket.py`, `tests/unit/test_friend_state.py` | Quyền riêng tư, race, giới hạn, realtime nhiều tab, mất kết nối, cache và shutdown |

Các đường dẫn backend trong bảng tính từ `backend/app/`, ngoại trừ `migrations/` và `tests/` tính từ `backend/`.

## 2. API và quy tắc cần kiểm tra

Base URL là `/api/v1`. Thành viên phải đang hoạt động và đã đổi mật khẩu bắt buộc; guest không dùng API bạn bè/chặn.

| Method | Path | Nội dung |
|---|---|---|
| GET | `/users/search?email=...` | Email đầy đủ sau chuẩn hóa; chỉ trả tối đa một người; bản thân/ẩn/không tồn tại/bị khóa/bị chặn đều trả items rỗng |
| POST | `/friends/requests` | Body `{to_user_id}`; 201; nếu có lời mời chiều ngược thì tự chấp nhận |
| GET | `/friends/requests?direction=incoming` hoặc `outgoing` | `{items:[{id,from,to,status,created_at}]}` |
| POST | `/friends/requests/{id}/accept` | 200 phần tử bạn bè; chỉ người nhận được chấp nhận |
| POST | `/friends/requests/{id}/decline` | 204; không báo người gửi |
| DELETE | `/friends/requests/{id}` | 204; người gửi hủy |
| GET | `/friends?q=&page=1&page_size=20` | Items + total/page/page_size, page_size tối đa 100, ưu tiên online rồi tên |
| DELETE | `/friends/{user_id}` | 204; xóa quan hệ hai chiều, báo người còn lại |
| GET/POST | `/blocks` | Danh sách chặn hoặc body `{user_id}` để chặn; POST 201, lặp lại không tạo bản trùng |
| DELETE | `/blocks/{user_id}` | 204; không khôi phục quan hệ cũ |

Payload người khác chỉ có ID, tên, URL thumbnail và dữ liệu quan hệ phù hợp; không trả email/ngày sinh. Từ chối không phát sự kiện và vẫn hiện `pending` ở danh sách người gửi tới TTL. Không trả `responded_at`. Lời mời bị che tính vào hạn mức đã gửi; hủy rồi gửi lại không bỏ qua được cooldown 24 giờ. Người nhận chủ động gửi ngược cho phép đồng ý ngay; các lời mời bị che trước đó được kết thúc để không xuất hiện lại sau khi hủy bạn.

Chặn hủy quan hệ và lời mời kết bạn giữa hai người, ẩn tìm kiếm cả hai chiều, không báo người bị chặn. Chặn không đưa người dùng ra khỏi phòng gọi hiện tại. Hủy lời mời gọi/chặn DM sẽ được nối khi E5/E4 có bảng và API tương ứng.

TTL được áp dụng ngay khi GET/chấp nhận; sweep khoảng 30 giây cập nhật các lời mời pending đã quá hạn. Kiểm tra hạn mức trong cùng giao dịch khóa cặp tài khoản để yêu cầu đồng thời không tạo hai quan hệ hoặc vượt số bạn.

## 3. Cấu hình và giới hạn

| Khóa | Mặc định | Khoảng |
|---|---|---|
| friends_enabled | true | Boolean |
| friend_search_enabled | true | Boolean |
| max_friends_per_user | 200 | 10–2000 |
| max_pending_friend_requests | 50 | 5–500 |
| friend_request_ttl_days | 30 | 1–365 |

Các khóa nằm trong nhóm truy cập của cấu hình hiện có, cập nhật qua admin và có audit như các cấu hình cũ. Public config trả hai cờ bạn bè. Phần cấu hình này được thực hiện ở E2 vì service cần áp dụng ngay; không đồng nghĩa đã hoàn tất E7.

Khi tắt bạn bè, không cho tìm/đọc danh sách/gửi/chấp nhận mới; vẫn cho từ chối/hủy, hủy kết bạn và quản lý chặn. Tìm kiếm tối đa 20/phút, 200/ngày mỗi tài khoản; thêm 60/phút, 600/ngày mỗi IP. Gửi tối đa 10/phút mỗi tài khoản, 30/phút mỗi IP. Lỗi hạn mức/rate/cooldown có mã riêng; 429 kèm Retry-After.

## 4. Luồng realtime và đồng bộ

1. Xác thực socket bằng phiên còn hiệu lực, tự vào `user:<UUID>`. Không nhận user room từ client; guest không tham gia.
2. Lời mời mới phát `friend_request_received` cho mọi tab người nhận. Chấp nhận phát `friend_added` cho cả hai; hủy bạn phát `friend_removed` cho người còn lại. Từ chối/chặn không có thông báo cho người gửi/bị chặn.
3. Đổi tên/ảnh phát `friend_profile_changed` cho bạn bè. Email/ngày sinh không đi trong payload.
4. Socket đầu tiên phát online; socket cuối cùng ngắt thì chờ 5 giây. Nối lại sớm hủy offline, không phát online lặp. HTTP danh sách bạn cũng giữ trạng thái trong khoảng chờ.
5. Tắt quyền online gửi `online:null` để xóa trạng thái cũ; sau đó không phát true/false. Bật lại gửi trạng thái hiện tại.
6. Thông báo best-effort, gửi sau commit; lỗi phát không biến API thành thất bại. Web tự lấy đủ trang `/friends` và hai chiều lời mời sau connect/reconnect; bỏ kết quả từ kết nối cũ, gộp yêu cầu làm mới khi có nhiều thông báo.

Snapshot web phát qua sự kiện trình duyệt `videocall:friends-synced` với `{friends,incoming,outgoing}`, lỗi là `videocall:friends-sync-error`. UI U5 sẽ dùng snapshot và các sự kiện Socket.IO để dựng màn hình. Module chưa gọi API DM/invites vì chúng chưa được triển khai.

Cache chỉ giữ cho tài khoản online, mất hiệu lực khi quan hệ/quyền thay đổi. Khi offline/shutdown, cache và timer được dọn; không cần Redis trong kiến trúc một worker hiện có.

## 5. Kết quả kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Backend hiện có + E2/E3 | **109 passed**, PostgreSQL thật, HTTP và Socket.IO thật |
| Migration | Upgrade head → check → downgrade base → upgrade head → check: đạt, không lệch model/schema |
| Phân quyền DB | Migration bằng tài khoản riêng; kiểm thử ứng dụng bằng app role hạn quyền |
| Lint/định dạng | Ruff check và format check: đạt |
| JavaScript | Kiểm tra cú pháp ba module thêm/sửa: đạt |
| Chrome và Edge | Snapshot ban đầu, hai tab nhận lời mời, mất mạng rồi đồng bộ lại, chấp nhận cập nhật cả hai tab: đạt |
| Lỗi trình duyệt | Không ghi nhận JavaScript runtime/CSP error trong lượt kiểm thử |
| Docker/local | Build đạt; migration local ở 0010, readiness 200 |
| Dữ liệu cũ | Đối chiếu tài khoản/mật khẩu/cấu hình trước–sau giữ nguyên; tài khoản thử trình duyệt đã dọn |

Kiểm thử dùng database riêng `videocall_phase2_test`. Downgrade chỉ chạy trên database này. Đã kiểm tra ẩn email, quyền sở hữu lời mời, từ chối im lặng, cooldown không vượt bằng hủy, TTL, unique/canonical DB, gửi hai chiều/nhân đôi/chặn đồng thời, chấp nhận không vượt hạn mức, các rate limit, nhiều tab, debounce offline, quyền riêng tư, chặn không kick phòng, HTTP bù event mất, lỗi phát không mất giao dịch, cache và dọn timer.

Lượt này chưa nghiệm thu bằng iPhone thực hay mạng di động. Không có thay đổi UI cần ảnh mockup mới. Tài liệu API đầy đủ nằm tại `docs/docs/02-api.md`; sự kiện tại `03-socket-events.md`.

## 6. Cách nghiệm thu

Mở `http://localhost:8000/docs`. Dùng hai tài khoản thử A/B, đăng nhập và Authorize lần lượt bằng access token của tài khoản thao tác.

1. A tìm email đầy đủ của B, gửi lời mời bằng ID. Kiểm tra B thấy incoming và A thấy outgoing.
2. B từ chối: B hết incoming, A vẫn thấy pending, gửi lại bị cooldown. Dùng một cặp tài khoản thử khác để kiểm tra chấp nhận hoặc gửi ngược tự chấp nhận.
3. Mở web trong hai trình duyệt/hai phiên cho hai tài khoản. Khi đã là bạn, kết nối realtime tự có ở sảnh; kiểm tra is_online bằng GET danh sách bạn. Ngắt một tab không làm offline nếu còn tab khác.
4. Tắt quyền online của B bằng PATCH `/me`; A nhận null. Thử chặn: danh sách bạn biến mất và hai bên tìm nhau đều rỗng; bỏ chặn không tự khôi phục quan hệ.
5. Ngắt mạng một phiên, thay đổi lời mời ở phiên còn lại rồi kết nối lại; web lấy snapshot mới qua HTTP.

Màn hình Bạn bè/Tin nhắn chưa nằm trong đợt E2/E3; kiểm tra nghiệp vụ qua Swagger/API và sự kiện realtime. Mã được đưa lên `feat/phase2` để review, không merge main trong yêu cầu này.
