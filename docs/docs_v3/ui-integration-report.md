# Tích hợp giao diện V3 vào hai web

Ngày kiểm tra: **18/11/2026**. Nhánh: **`feat/update-ui-v3`**.

## Phạm vi theo xác nhận của người dùng

Người dùng duyệt trang mẫu U1 và yêu cầu thay toàn bộ giao diện web người dùng, web quản trị, đồng thời giữ các chức năng đã làm. Đợt này áp dụng thiết kế đã duyệt vào các màn hình hiện có. Các đường dẫn `/`, `/lobby`, `/room` và `/admin/*` tiếp tục hoạt động; không thêm migration hoặc chức năng backend thuộc E1–E7.

| Khu vực | Giao diện được áp dụng | Chức năng được giữ |
|---|---|---|
| Đăng nhập người dùng | Giới thiệu hai cột, thẻ đăng nhập, đăng ký/khách mở rộng, sáng/tối | Đăng ký, đăng nhập, khách, thông báo bảo trì, xác nhận/hủy chuyển thiết bị |
| Sảnh | Sidebar, điều hướng đáy trên điện thoại, thẻ vào/tạo phòng, danh sách phòng dạng card, thông tin tài khoản | Tạo meeting/livestream, mật khẩu phòng, vào bằng mã, phòng của tôi, đổi mật khẩu bắt buộc, hiện diện, đăng xuất |
| Phòng gọi | Màn hình chờ, lưới video, thanh điều khiển, tab Chat/Thành viên | Camera/mic, P2P, host tắt media, chia sẻ màn hình, chat/lịch sử, chỉ số mạng, sao chép mã, rời phòng |
| Livestream | Dùng cùng khu vực cuộc gọi và thành phần mới | Phát/xem qua SFU, phát lại video nếu bị chặn autoplay, đổi người phát, kết nối lại |
| Quản trị | Sidebar có nhãn ADMIN, chủ đề tối mặc định, bố cục riêng, bảng/biểu mẫu/thẻ chỉ số | Đăng nhập, phân quyền, cookie phiên, CSRF, tài khoản, phiên, mật khẩu tạm, phòng/kick/đóng, cấu hình, nhật ký, phân trang |
| Dashboard | Thẻ hiện diện nổi bật và các chỉ số thật | SSE cập nhật số phòng có người và tài khoản online; số tài khoản, phòng mở, người trong phòng, socket, thống kê đăng ký |

Không thêm các mục chưa có backend như bạn bè, nhắn tin riêng, lịch sử cuộc gọi hoặc báo cáo mới. Đây là tích hợp giao diện hiện có theo yêu cầu mới, không phải tuyên bố hoàn thành toàn bộ U2–U7 trong lộ trình mở rộng.

## Cách triển khai

- Hai web dùng chung `tokens.css`, `base.css`, `components.css`, phông Inter và sprite SVG cục bộ của U1. `client/styles.css` và `admin.css` chỉ giữ phần bố cục riêng.
- Giữ toàn bộ ID DOM cũ và tên trường biểu mẫu của ba trang người dùng. Các module API, refresh/thu hồi phiên, WebRTC, SFU, chat và stats tiếp tục thực hiện nghiệp vụ hiện có.
- Chỉ bổ sung điều hướng tab Chat/Thành viên và hành vi giữ focus cho hộp thoại ở client. Thẻ phòng vẫn lấy dữ liệu thật từ `/rooms/mine`, gán tên bằng `textContent`.
- Xác nhận thao tác quản trị dùng hộp thoại cùng thiết kế U1, chuyển tiếp yêu cầu HTMX hiện có sau khi xác nhận. Hủy/Esc không gửi thao tác. Chính sách CSP tiếp tục chặn script ngoài nguồn và inline; bổ sung `font-src 'self'` cho Inter và favicon dạng data.
- Sáng/tối/theo hệ thống lưu riêng cho người dùng và admin. Mặc định người dùng sáng, admin tối. Khóa theme cũ được giữ; lựa chọn U1 có khóa riêng.
- Giữ cấu hình tên, màu và phông đã lưu. Màu mặc định trong schema đổi sang chàm `#4f46e5`; không ghi đè giá trị tùy chỉnh trong DB. Màu nút tùy chỉnh chọn chữ đen/trắng theo độ chói như chức năng V2.
- Bộ đếm hiện diện admin tiếp tục dùng SSE đã có; không đổi sang cơ chế polling và không thêm số liệu giả.

## Kiểm tra và kết quả

### Backend

**46 bài kiểm thử đều đạt**, chạy trong container riêng, database thử nghiệm `videocall_ui_v3_test`; cấu hình SFU tắt cho suite để khớp môi trường CI. Bao gồm auth/chuyển thiết bị, CSRF/phiên admin, thao tác admin, phòng/signaling, chat và TURN. Không chạy suite này trên database người dùng.

Ruff lint, Ruff format và kiểm tra cú pháp JS đạt. Không thêm schema/migration DB trong đợt giao diện này.

### Trình duyệt

Kiểm tra bằng Playwright trên **Chrome và Edge**, với **1440 / 900 / 390 px** và cả **sáng / tối**. 12 trạng thái màn hình cho mỗi trình duyệt, tổng cộng **144 tổ hợp**:

`login`, `lobby`, `precall`, `call`, `admin-login`, `dashboard`, `admin-users`, `admin-rooms`, `admin-settings`, `admin-audit`, `admin-user`, `livestream`.

[Kết quả toàn bộ tổ hợp](assets/integration/checks.json).

Các kiểm tra trực tiếp với backend thật đã qua ở cả hai trình duyệt:

- Đăng ký, đăng nhập, tên khách; tạo phòng riêng và tham gia bằng mã/mật khẩu.
- Cuộc gọi P2P nhận và giải mã khung hình hai chiều. Bật/tắt mic, camera; hiện chỉ số mạng; tab thành viên và chat.
- Tin nhắn tiếng Việt chứa `<b>chat</b>` được nhận nguyên văn, không tạo thẻ HTML.
- Dashboard nhận sự kiện SSE và hiển thị số phòng đang hoạt động thật.
- Điều hướng HTMX qua tài khoản, phòng, cấu hình và nhật ký; lọc và xem chi tiết tài khoản.
- Hủy xác nhận thu hồi phiên bằng Esc; thao tác không được gửi.
- Kiểm tra bổ sung nhánh xác nhận thật: xóa một tài khoản fixture riêng qua dialog, yêu cầu HTMX có CSRF thành công, tài khoản biến mất khỏi danh sách.
- Host phát livestream qua SFU, bên xem nhận và giải mã video; rời phòng quay lại sảnh.
- Các trang không tràn ngang toàn màn hình. Bảng và menu hẹp cuộn trong vùng riêng; Inter tải được.

Không ghi nhận lỗi JavaScript hoặc CSP. Lần mở trang chưa có phiên có thể trả 401 cho yêu cầu khôi phục phiên — đây là hành vi auth hiện có, được bộ test nhận biết.

Luồng hình/âm thanh kiểm thử được tạo bằng Canvas và Web Audio trong bộ test, rồi truyền qua WebRTC/SFU thật. Không mở camera/mic vật lý. Các lượt chụp dùng dữ liệu thử thật tạo trong backend; hình media có chữ “UI media test”.

Đã dọn 7 tài khoản và 10 phòng do các lượt test tạo trong DB dev, theo đúng mẫu email và người sở hữu fixture. Fixture bổ sung cho bài xác nhận đã được xóa qua web quản trị. Cấu hình và tài khoản người dùng có sẵn được giữ.

### Phạm vi chưa được kiểm chứng bằng phần cứng

Chưa nghiệm thu Safari trên iPhone thật, camera/mic vật lý, chia sẻ màn hình thật và hai mạng khác nhau. Các luồng này giữ bộ xử lý cũ; vẫn cần thử trực tiếp khi có thiết bị/mạng tương ứng. Thay đổi này không tuyên bố đạt Lighthouse hoặc kiểm toán a11y toàn ứng dụng.

## Ảnh đại diện

| Màn hình | Ảnh |
|---|---|
| Đăng nhập người dùng, laptop sáng | [Xem ảnh](assets/integration/chrome-login-desktop-light.png) |
| Sảnh, laptop tối | [Xem ảnh](assets/integration/chrome-lobby-desktop-dark.png) |
| Sảnh, điện thoại sáng | [Xem ảnh](assets/integration/msedge-lobby-phone-light.png) |
| Cuộc gọi, laptop tối | [Xem ảnh](assets/integration/chrome-call-desktop-dark.png) |
| Cuộc gọi, điện thoại sáng | [Xem ảnh](assets/integration/chrome-call-phone-light.png) |
| Livestream, điện thoại tối | [Xem ảnh](assets/integration/msedge-livestream-phone-dark.png) |
| Đăng nhập admin, điện thoại tối | [Xem ảnh](assets/integration/msedge-admin-login-phone-dark.png) |
| Dashboard, laptop tối | [Xem ảnh](assets/integration/chrome-dashboard-desktop-dark.png) |
| Dashboard, điện thoại sáng | [Xem ảnh](assets/integration/msedge-dashboard-phone-light.png) |

Ảnh có thể hiện tên dự án tùy chỉnh đang lưu trong cấu hình; đây là chủ đích giữ chức năng nhận diện của V2.

## Mở bản giao diện mới

Mở Docker Desktop rồi chạy ở thư mục dự án:

```powershell
docker compose up --build --wait
```

Web người dùng: <http://localhost:8000/>. Quản trị: <http://localhost:8000/admin>. Trang mẫu U1 vẫn có ở `/styleguide` khi `ENV=dev`.

## Chạy lại kiểm tra trình duyệt

```powershell
npm install --prefix .lan/u1-tools --no-save --no-package-lock --no-audit --no-fund playwright@1.65.1
$env:UI_BASE_URL = 'http://localhost:8000'
node tools/check-web-ui.cjs
```

Cần Chrome, Edge, backend/PostgreSQL/coturn/SFU đang hoạt động và tính năng đăng ký/khách/meeting/livestream được bật. Công cụ dùng admin demo `admin`/`admin123` ở môi trường dev; đặt `UI_ADMIN_LOGIN`, `UI_ADMIN_PASSWORD` nếu dùng tài khoản thử riêng. Công cụ tạo tài khoản `ui-<timestamp>-<browser>@example.com` và phòng thử; nên chạy trên môi trường nghiệm thu riêng. Các lượt thử dày có thể chạm giới hạn đăng ký hiện có; không nới giới hạn để chạy test. Ảnh và log mặc định ở `.lan/web-ui-results`, không tự đưa toàn bộ vào Git.
