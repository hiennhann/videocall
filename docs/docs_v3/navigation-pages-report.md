# Mỗi mục điều hướng là một trang riêng

Ngày thực hiện: **18/11/2026**. Nhánh: **`feat/update-ui-v3`**.

Người dùng xác nhận tách các mục menu và Vào/Tạo phòng thành trang riêng; Chat/Thành viên tiếp tục ở trong phòng gọi.

## Đường dẫn và nội dung

| Mục | URL | HTML | Nội dung chính |
|---|---|---|---|
| Trang chủ | `/lobby` | `client/lobby.html` | Các lối tắt đến bốn trang chức năng |
| Phòng của tôi | `/rooms` | `client/rooms.html` | Danh sách phòng đã tạo, trạng thái rỗng, liên kết vào/tạo |
| Tài khoản | `/account` | `client/account.html` | Tên, email, vai trò và biểu mẫu đổi mật khẩu hiện có |
| Vào phòng | `/rooms/join` | `client/join.html` | Biểu mẫu nhập mã phòng |
| Tạo phòng | `/rooms/create` | `client/create.html` | Chọn meeting/livestream, tên và mật khẩu phòng |

Mỗi URL trả một tài liệu HTML riêng. Trang chủ không chứa danh sách phòng hoặc biểu mẫu ẩn của các mục khác. Trang phòng không chứa biểu mẫu vào/tạo; trang tài khoản không chứa phần quản lý phòng. Menu không còn dùng `#rooms-sidebar`, `#account-sidebar` hoặc tab Vào/Tạo để đổi nội dung trong cùng tài liệu.

Các trang dùng chung thiết kế, khung menu và module `workspace.js` cho phiên đăng nhập, cấu hình giao diện và trạng thái kết nối. Mỗi trang có module JS nghiệp vụ riêng, chỉ gắn sự kiện và tải dữ liệu cần cho trang đó.

## Quản trị và phòng gọi

- Menu quản trị dùng các URL hiện có `/admin`, `/admin/rooms`, `/admin/users`, `/admin/settings`, `/admin/audit` và điều hướng tải trang đầy đủ (`hx-boost="false"` trên menu). Mỗi trang có nội dung riêng từ mẫu Jinja tương ứng.
- Các biểu mẫu quản trị vẫn dùng HTMX/CSRF và hộp thoại xác nhận hiện có.
- `/room?code=...` vẫn là trang cuộc gọi riêng. Tab Chat/Thành viên ở cùng trang đó để giữ kết nối cuộc gọi, đúng lựa chọn của người dùng.
- `/`, đăng ký, khách, xác nhận chuyển thiết bị, phiên cookie và các endpoint nghiệp vụ được giữ.

## Giữ quyền và phiên đăng nhập

- Người chưa đăng nhập được chuyển về `/?next=...` khi mở các trang người dùng. Đăng nhập, vào bằng tên khách hoặc xác nhận chuyển thiết bị thành công sẽ về đúng trang đó. Mở trang đăng nhập bình thường sẽ vào `/lobby` sau khi đăng nhập.
- Người bắt buộc đổi mật khẩu được chuyển tới `/account`, kể cả khi mở thẳng `/rooms/create`; sau đổi mật khẩu có thể tiếp tục vào các trang khác.
- Khách được vào bằng mã, xem tài khoản khách và trang phòng; không hiện lối tắt tạo phòng. Mở trực tiếp trang tạo phòng bằng phiên khách hiển thị thông báo và không hiện biểu mẫu.
- Mỗi tài liệu khôi phục phiên bằng cơ chế refresh-cookie hiện có. Khi chuyển trang, socket hiện diện của trang cũ đóng; trang mới kết nối lại. Back/Forward khôi phục trang từ cache sẽ kết nối lại hiện diện.
- Các lựa chọn sáng/tối, tên, màu và phông tiếp tục áp dụng trên từng trang.

### Bắt buộc có phiên ở máy chủ cho cả hai web

Theo xác nhận bổ sung của người dùng, **khách vẫn được dùng**, nhưng phải nhập tên để nhận phiên khách trước khi mở web người dùng. Máy chủ kiểm tra trước khi trả HTML cho `/lobby`, `/rooms`, `/account`, `/rooms/join`, `/rooms/create`, `/room` và các bản HTML trực tiếp dưới `/client/`. Chưa đăng nhập trả HTTP `303` về trang đăng nhập, không trả HTML ứng dụng để chờ JavaScript chuyển trang.

- Web đăng nhập tài khoản, xác nhận chuyển thiết bị và refresh cấp cookie `vc_user_page_access`, có `HttpOnly`, `Secure`, `SameSite=Strict`, đường dẫn `/`. Refresh token giữ phạm vi cũ `/api/v1/auth`.
- Mỗi yêu cầu trang của tài khoản kiểm tra chữ ký/hạn token, tài khoản còn hoạt động và session family thuộc phạm vi `user` chưa bị thu hồi. Cookie sao chép sau đăng xuất/thu hồi hoặc tài khoản bị khóa không mở được trang.
- Web khách gửi `client_type: "web"` khi nhập tên để nhận cookie trang. Quyền khách vẫn giới hạn như cũ. Guest API mặc định giữ chế độ JSON cho client khác. Khi đăng xuất, cả tài khoản và khách đều gọi server để xóa cookie trang.
- Trường hợp mất cookie hoặc chính sách không còn cho phép phiên khách, `login_required=1` giúp trang đăng nhập xóa trạng thái khách cũ ở trình duyệt, tránh tự chuyển trang lặp lại.
- Trang HTML bảo vệ có `Cache-Control: no-store`, `Vary: Cookie`. Chuyển thiết bị, phiên hết hạn, đổi mật khẩu bắt buộc và khóa tài khoản tiếp tục được kiểm tra tại server/API.
- Web quản trị tiếp tục dùng cookie phạm vi `/admin`, kiểm tra tài khoản admin đang hoạt động và phiên `admin`. Phiên người dùng/khách không mở được các trang quản trị; token của phiên admin cũng không được dùng làm cookie của web người dùng.
- Trang đăng nhập/đăng ký/tên khách và tài nguyên CSS/JS/phông là công khai; các endpoint API giữ xác thực và phân quyền hiện có. Trang mẫu thành phần vẫn chỉ là công cụ dev theo U1.

Kiểm tra bổ sung: **54 bài backend đạt**, gồm cookie giả/hết hạn/đã thu hồi, tài khoản bị khóa, yêu cầu đổi mật khẩu, phân tách hai phiên và chế độ khách. Chrome và Edge đã kiểm tra HTTP trực tiếp không qua JS, sáu URL ứng dụng, sáu URL HTML, năm trang admin; đăng xuất rồi Back không mở lại trang nội bộ. Kiểm tra riêng ở cả hai trình duyệt xác nhận mất cookie khách sẽ trở về đăng nhập và xóa trạng thái cũ, không lặp chuyển trang.

### Nối với trang đăng nhập

`client/js/auth-navigation.js` dùng chung cho kiểm tra phiên và điều hướng sau đăng nhập. Các trang được phép là `/lobby`, `/rooms`, `/account`, `/rooms/join`, `/rooms/create`, `/room`; tham số mã phòng được giữ khi mở liên kết cuộc gọi. URL ngoài nguồn hiện tại, URL không hợp lệ và đường dẫn khác dùng đích mặc định `/lobby`.

Đăng ký giữ trang đích trong khi yêu cầu người dùng đăng nhập. Nhập sai mật khẩu hoặc hủy chuyển thiết bị không làm mất trang đích. Người đã có phiên hợp lệ khi mở `/?next=...` đi thẳng tới trang tương ứng. Đăng xuất vẫn kết thúc phiên và về `/` với thông báo; trang quản trị tiếp tục dùng đăng nhập `/admin/login` và phiên quản trị riêng.

Kiểm tra bổ sung bằng `tools/check-login-navigation.cjs` trên Chrome và Edge: sáu đường dẫn khi chưa đăng nhập, tám trường hợp đích không hợp lệ, đăng ký/đăng nhập, mật khẩu sai, giữ phiên qua các trang và tải lại, khôi phục phiên, đăng xuất, khách và xác nhận/hủy chuyển thiết bị. [Kết quả kiểm tra đăng nhập](assets/pages/login-navigation-checks.json).

## Kiểm tra

- **47 bài backend đạt**, gồm kiểm tra riêng từng URL và việc không nhúng nội dung của trang khác. **7 unit test đạt** khi chạy riêng; Ruff và cú pháp JS đạt.
- **192 tổ hợp hiển thị** trên Chrome và Edge, ba độ rộng 1440/900/390 px, sáng/tối, 16 trạng thái màn hình. [Kết quả](assets/pages/checks.json).
- Kiểm tra click menu thay tài liệu thật (biến đánh dấu của tài liệu cũ không còn), đúng URL, Back/Forward, tải lại và mở trực tiếp trang tài khoản.
- Kiểm tra riêng luồng admin đặt mật khẩu tạm → đăng nhập → chuyển tới `/account` → chặn tạo phòng trước khi đổi → đổi mật khẩu → mở được trang tạo phòng. Dùng tài khoản fixture do bộ test tạo.
- Kiểm tra khách bị chặn trang tạo; đăng ký/đăng nhập/khách, tạo phòng riêng, vào bằng mã/mật khẩu, video P2P hai chiều, chat, mic/camera, chỉ số mạng, thành viên và livestream SFU vẫn qua kiểm tra trình duyệt.
- Điều hướng quản trị, Dashboard SSE, biểu mẫu CSRF và nhánh Hủy của hộp thoại tiếp tục qua kiểm tra.

Đã dọn 5 tài khoản và 8 phòng do các lượt kiểm tra này tạo, theo mẫu email fixture và đúng người sở hữu phòng. Sau đổi mật khẩu bắt buộc, hiện diện kết nối lại mà không tạo socket trùng trong cùng tài liệu.

Luồng media vẫn dùng hình/âm thanh tổng hợp và WebRTC/SFU thật như đợt tích hợp trước. Nghiệm thu camera/mic vật lý, Safari trên iPhone và hai mạng khác nhau chưa nằm trong các kết quả tự động này.

Bộ kiểm tra `tools/check-web-ui.cjs` đã cập nhật theo các trang mới. Hai lượt Chrome/Edge được cách nhau 60 giây để tuân thủ giới hạn refresh 30 yêu cầu/phút/IP hiện có; không thay đổi giới hạn trong sản phẩm.

## Ảnh các trang

| Trang | Ảnh |
|---|---|
| Trang chủ, laptop sáng | [Xem ảnh](assets/pages/chrome-lobby-desktop-light.png) |
| Phòng của tôi, laptop tối | [Xem ảnh](assets/pages/chrome-rooms-desktop-dark.png) |
| Tài khoản, điện thoại sáng | [Xem ảnh](assets/pages/msedge-account-phone-light.png) |
| Vào phòng, điện thoại tối | [Xem ảnh](assets/pages/msedge-join-phone-dark.png) |
| Tạo phòng, laptop sáng | [Xem ảnh](assets/pages/chrome-create-desktop-light.png) |

Chạy bản mới bằng `docker compose up --build --wait`, rồi đăng nhập và dùng menu. Nhánh được cập nhật để duyệt; chưa merge `main`.
