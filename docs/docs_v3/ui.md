# UI: Tối ưu giao diện

> Bổ sung cho bộ `docs/` và `docs_v3/extend.md`. Trạng thái: **U1 đã được duyệt; đã tích hợp giao diện mới vào hai web cho các chức năng hiện có ngày 18/11/2026**. Xem [báo cáo U1](u1-report.md) và [báo cáo tích hợp](ui-integration-report.md). Các chức năng mở rộng phụ thuộc E1–E7 vẫn theo lộ trình riêng.
> Nguồn tham chiếu: ảnh mockup gồm hai giao diện **"ConnectV – Webapp Người dùng"** (nền sáng) và **"ConnectV – Trang Quản trị Admin (Tối giản)"** (nền tối).
> Quy tắc làm việc giữ nguyên: thiết kế trước, code sau; tài liệu là bản sống.

> **Chốt bổ sung 18/11/2026:** Các mục menu và Vào/Tạo phòng dùng **trang HTML riêng, URL riêng, điều hướng tải trang đầy đủ**. Thay phương án một trang/hash router ở mục 5.1, 9.1 và U2 cho các màn hình hiện có. Chat/Thành viên vẫn là hai panel trong phòng gọi theo xác nhận của người dùng. [Ánh xạ đường dẫn và kiểm thử](navigation-pages-report.md).

## 1. Mục tiêu và phạm vi

1. Đổi giao diện **web người dùng** và **trang quản trị** theo phong cách của mockup.
2. Thiết kế giao diện cho các chức năng mở rộng ở `extend.md`: bạn bè, tin nhắn, lời mời gọi, lịch sử cuộc gọi, hồ sơ.
3. Giữ nguyên **kiến trúc kỹ thuật đã chốt**: client là HTML/CSS/JS thuần không cần build (D21); trang admin là Jinja2 + HTMX (D17). Chỉ thay đổi diện mạo và tổ chức màn hình, **không đổi backend**.

**Nguyên tắc khi dùng mockup:** mockup là **hướng thị giác** (màu, bố cục, mật độ thông tin), không phải đặc tả tính năng. Nhiều thành phần trong mockup (lịch họp, bản ghi, transcript, băng thông Gbps, QoS) **chưa có dữ liệu ở backend**. Mục 8 ghi rõ từng thành phần sẽ hiển thị gì ở bản đầu và cái nào để `idea.md`.

## 2. Phân tích mockup

> Ảnh có độ phân giải thấp, một số chữ nhỏ có thể đọc chưa chính xác. Danh sách dưới đây là những gì nhìn thấy được; hãy đối chiếu lại khi có bản gốc.

### 2.1 Giao diện người dùng (nền sáng)

- **Sidebar trái:** logo "ConnectV" kèm nhãn "Workspace"; menu gồm *Trang chủ*, *Phòng họp* (có nhãn "Live"), *Lịch họp* (có số), *Biên bản họp*, *Cài đặt*; thẻ người dùng ở đáy (ảnh, tên "Mai Linh", chức danh).
- **Đầu trang:** dòng ngày giờ kèm trạng thái "Hệ thống sẵn sàng"; lời chào "Xin chào, Mai Linh 👋"; câu mô tả số cuộc họp sắp tới và phòng đang mở; hai nút: **"Tham gia bằng mã"** (phụ) và **"Tạo phòng họp mới"** (chính, màu chàm).
- **"Cuộc họp hôm nay":** ba thẻ ngang, mỗi thẻ có nhãn trạng thái nhỏ, tiêu đề, giờ, mô tả ngắn, cụm ảnh người tham gia và nút (*Vào họp ngay* hoặc *Xem chi tiết*).
- **"Biên bản & Lịch sử gần đây":** danh sách dòng gồm biểu tượng, tiêu đề, thông tin phụ (ngày, thời lượng, số người, người chủ trì) và nút hành động (*Xem bản ghi*, *Tải Transcript*), có liên kết "Xem tất cả".
- **Chân trang:** trạng thái kết nối máy chủ, phiên bản, liên kết bảo mật/hỗ trợ.

### 2.2 Giao diện quản trị (nền tối)

- **Sidebar trái:** logo kèm nhãn "ADMIN"; menu *Tổng quan*, *Phòng họp trực tiếp* (có số), *Thành viên*, *Báo cáo & Phân tích*, *Cấu hình & Bảo mật*; thẻ quản trị viên ở đáy (tên, vai trò "Super Admin", nút đăng xuất).
- **Đầu trang:** tiêu đề "Tổng quan hệ thống", nhãn trạng thái "Hệ thống hoạt động bình thường", nút *Xuất báo cáo* (phụ) và *Tạo phòng họp* (chính).
- **Ba thẻ chỉ số:** *Phòng họp đang chạy* (số lớn + mức thay đổi), *Băng thông số* (số / công suất + thanh tiến độ), *Độ ổn định QoS* (phần trăm + nhãn).
- **Bảng "Các phòng họp đang diễn ra":** cột tên phòng/chủ trì, số người, băng thông, trạng thái bảo mật, thao tác (*Chi tiết*, *Ngắt phòng* dạng viền đỏ); có nút "Thời gian thực".

### 2.3 Đặc điểm thị giác chung

- Bố cục **sidebar cố định + vùng nội dung**, thẻ (card) bo góc lớn, đường viền mảnh, bóng đổ nhẹ.
- Một **màu nhấn chính** (chàm/tím xanh) dùng cho nút chính, mục menu đang chọn, liên kết.
- Màu trạng thái: xanh lá (tốt, trực tiếp), cam (cảnh báo), đỏ (nguy hiểm, ngắt phòng).
- **Nhãn tiêu đề cột và nhãn thẻ chỉ số viết hoa, chữ nhỏ, giãn chữ.**
- Mật độ thông tin vừa phải, nhiều khoảng trắng ở giao diện sáng; dày hơn ở giao diện quản trị.

## 3. Hệ thống thiết kế (design tokens)

> Bảng dưới là màu đang triển khai trong U1, lấy bảng màu dự kiến làm cơ sở và điều chỉnh tương phản. Repo chưa có hai ảnh mockup ConnectV gốc, nên **chưa đối chiếu bằng công cụ chọn màu trên ảnh**. Các giá trị chính xác nằm trong `client/css/tokens.css`; kết quả đo ở [báo cáo U1](u1-report.md). Tên sản phẩm đã chốt: **Videocall**.

### 3.1 Màu sắc

| Token | Giao diện sáng (người dùng) | Giao diện tối (admin) |
|---|---|---|
| `--bg-app` | `#F3F4F8` | `#0B0F1A` |
| `--surface` (thẻ) | `#FFFFFF` | `#111827` |
| `--surface-2` (nền phụ) | `#F8FAFC` | `#161E2E` |
| `--border` (trang trí) | `#E6E8EF` | `#2A3448` |
| `--border-control` (ô nhập/nút phụ) | `#778399` | `#71839E` |
| `--text` | `#0F172A` | `#E5E7EB` |
| `--text-muted` | `#526277` | `#A2AEC2` |
| `--primary` | `#4F46E5` | `#595DE3` |
| `--primary-hover` | `#4338CA` | `#6264E9` |
| `--primary-soft` (nền nhạt) | `#EEF2FF` | `#202846` |
| `--primary-text` (chữ trên nền nhạt) | `#4338CA` | `#C7D2FE` |
| `--on-primary` | `#FFFFFF` | `#FFFFFF` |
| `--focus` | `#4F46E5` | `#A5B4FC` |
| `--success` / soft | `#166534` / `#DCFCE7` | `#4ADE80` / `#102D23` |
| `--warning` / soft | `#92400E` / `#FEF3C7` | `#FBBF24` / `#352914` |
| `--danger` / soft | `#B91C1C` / `#FEE2E2` | `#FCA5A5` / `#3B2029` |
| `--danger-fill` / `--on-danger` | `#B91C1C` / `#FFFFFF` | `#B91C1C` / `#FFFFFF` |
| `--progress-track` | `var(--border)` | `var(--surface-2)` |

Chữ trên trạng thái và nút chính được đo riêng, kể cả hover. `--border` chỉ phân nhóm nội dung; thành phần cần nhận biết viền dùng `--border-control`. Bảng màu này dùng cho bộ thành phần mới; CSS V2 chỉ chuyển sang tokens khi thực hiện các bước tích hợp U2–U4.

Quy ước dùng: nút **nguy hiểm** (Ngắt phòng, Xóa) ở dạng **viền + chữ đỏ**, chỉ đổ nền đỏ khi nằm trong hộp thoại xác nhận. Không truyền đạt trạng thái chỉ bằng màu (luôn kèm chữ hoặc biểu tượng).

### 3.2 Chữ

| Thành phần | Cỡ / dòng | Độ đậm | Ghi chú |
|---|---|---|---|
| Lời chào, số liệu lớn | 28-36 / 1,2 | 700 | Số trên thẻ chỉ số admin |
| Tiêu đề mục (H2) | 20 / 28 | 600 | "Cuộc họp hôm nay" |
| Tiêu đề thẻ (H3) | 16 / 24 | 600 | |
| Thân bài | 14 / 22 | 400 | |
| Chữ phụ | 12 / 18 | 400-500 | Thời gian, mô tả ngắn |
| **Nhãn viết hoa** | 11 / 16, giãn chữ 0,06em | 600 | Tiêu đề cột bảng, nhãn thẻ chỉ số |

Phông: **Inter** (hỗ trợ đầy đủ dấu tiếng Việt; ⚠ kiểm tra lại hiển thị các tổ hợp dấu khi làm), dự phòng `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. **Tự lưu phông (woff2) trong dự án**, không nạp từ dịch vụ bên ngoài (giữ riêng tư và phù hợp chính sách CSP). Số liệu dùng `font-variant-numeric: tabular-nums` để cột số thẳng hàng.

### 3.3 Khoảng cách, bo góc, bóng đổ, biểu tượng

- **Khoảng cách:** thang 4 px (`4, 8, 12, 16, 24, 32, 48`).
- **Bo góc:** nhỏ 8 px (nút, ô nhập), vừa 12 px (thẻ), lớn 16 px (khung lớn, hộp thoại), tròn hoàn toàn cho chip và ảnh đại diện.
- **Bóng đổ:** nhẹ ở giao diện sáng (`0 1px 2px` và `0 4px 12px` độ mờ thấp); giao diện tối dựa vào viền mảnh thay vì bóng.
- **Biểu tượng:** nét đơn giản 20 px, kiểu đường viền (line icons), đặt thành **một tệp sprite SVG** trong dự án, dùng `currentColor` để ăn theo màu chữ.
- **Chuyển động:** 120-200 ms cho hover/mở hộp thoại; tắt khi `prefers-reduced-motion`.

### 3.4 Chủ đề (theme)

- Web người dùng: **sáng** mặc định; tùy chọn **tối** và **theo hệ thống** (lưu trong `localStorage` của client, không cần backend).
- Trang admin: **tối** mặc định, cho phép chuyển sáng.
- Cách làm: toàn bộ màu là biến CSS trên `:root`, đổi bằng thuộc tính `data-theme` ở `<html>`. Mọi thành phần chỉ dùng biến, **không ghi màu cố định**.

## 4. Thư viện thành phần

Viết bằng HTML/CSS thuần (và vài hàm JS nhỏ), dùng chung cho cả web người dùng và admin.

| Thành phần | Biến thể / trạng thái chính |
|---|---|
| **Nút** | chính, phụ (viền), mờ (ghost), nguy hiểm (viền đỏ), kích cỡ S/M/L, có biểu tượng, đang tải |
| **Ô nhập, chọn, công tắc (toggle), hộp kiểm** | mặc định, hover, focus, lỗi (kèm thông báo), vô hiệu |
| **Nhãn trạng thái (chip/badge)** | trung tính, chính, thành công ("Trực tiếp"), cảnh báo, nguy hiểm; nhãn số (số lời mời, tin chưa đọc) |
| **Thẻ (card)** | thẻ thường, thẻ có hành động, thẻ chỉ số (admin) |
| **Ảnh đại diện (avatar)** | cỡ 24/32/40/64/96; ảnh hoặc **chữ cái đầu với màu sinh từ `user_id`**; chấm trực tuyến; **cụm chồng ảnh** (`+3`) |
| **Mục menu bên** | thường, đang chọn, có nhãn/số, thu gọn chỉ biểu tượng |
| **Bảng** | tiêu đề viết hoa nhỏ, hàng hover, cột thao tác, phân trang, trạng thái rỗng/đang tải |
| **Tab** | ngang, có số đếm |
| **Hộp thoại (modal) và ngăn kéo (drawer)** | có khóa focus, đóng bằng `Esc` |
| **Thông báo nổi (toast)** | thành công, lỗi, thông tin; **thẻ lời mời cuộc gọi** (có đếm ngược) |
| **Menu thả xuống (dropdown)** | menu hành động, chuông thông báo |
| **Thanh tiến độ** | thẻ băng thông (admin), đang tải ảnh |
| **Trạng thái rỗng** | biểu tượng + câu giải thích + nút hành động |
| **Khung chờ (skeleton)** | cho danh sách và thẻ khi đang tải |

Mọi thành phần có đủ: `hover`, `focus-visible` (viền rõ 2 px), `disabled`, `loading`.

## 5. Web người dùng: khung giao diện

### 5.1 Cấu trúc trang

| Trang | Tệp | Vai trò |
|---|---|---|
| Đăng nhập, đăng ký, vào bằng tên khách | `index.html` | Chưa xác thực |
| **Ứng dụng chính** (khung sidebar + các màn hình) | `app.html` | Đã xác thực; chuyển màn hình bằng địa chỉ dạng `#/home`, `#/friends`... mà không tải lại trang |
| **Phòng gọi** (toàn màn hình) | `room.html` | Giữ riêng vì cần toàn bộ khung hình và không bị gián đoạn khi điều hướng |

`app.html` giữ **kết nối Socket.io** xuyên suốt khi chuyển màn hình (nhận lời mời, tin nhắn, trạng thái online). Khi vào phòng gọi, mở `room.html` (cùng tab hoặc tab mới, chốt ở U3).

### 5.2 Điều hướng (sidebar)

| Mục | Màn hình | Nhãn/số | Có từ bước |
|---|---|---|---|
| Trang chủ | Home | | A5 |
| Phòng họp | Phòng của tôi, vào bằng mã | Nhãn **Live** khi có phòng đang mở | A4 |
| **Bạn bè** | Danh sách, lời mời, tìm kiếm | Số lời mời đến | E2 |
| **Tin nhắn** | Hộp thư | Số tin chưa đọc | E4 |
| **Lịch sử** | Lịch sử cuộc gọi | | E6 |
| Cài đặt | Hồ sơ, bảo mật, quyền riêng tư, giao diện | | E1 |

Khác với mockup: mục **"Lịch họp"** chưa có ở bản đầu (cần tính năng đặt lịch, xem `idea.md` I-01) và **"Biên bản họp"** được thay bằng **"Lịch sử"** (mục 8). Mục chưa sẵn sàng **ẩn đi**, không để mục "sắp ra mắt" bấm không có gì.

Thẻ người dùng ở đáy sidebar: ảnh đại diện, họ tên, email (mockup hiển thị chức danh; chức danh để `idea.md`), bấm vào mở Cài đặt.

### 5.3 Thanh trên và chân trang

- **Thanh trên** (trong vùng nội dung): ngày hiện tại và trạng thái ("Đã kết nối" khi Socket.io đang nối; "Đang kết nối lại…" khi mất kết nối), ô tìm nhanh (tìm bạn trong danh sách, tùy chọn), **chuông thông báo** (mục 6.7).
- **Chân trang:** trạng thái kết nối máy chủ, độ trễ ping của Socket.io (ms), phiên bản ứng dụng (lấy từ mã build). Không ghi cứng tên vùng máy chủ như mockup.

### 5.4 Đáp ứng kích thước màn hình

| Chiều rộng | Bố cục |
|---|---|
| ≥ 1200 px | Sidebar đầy đủ (≈ 248 px), nội dung tối đa ≈ 1200 px |
| 768-1199 px | Sidebar thu gọn còn biểu tượng (≈ 72 px), chữ hiện khi rê chuột |
| < 768 px | **Thanh điều hướng dưới đáy** 5 mục (Trang chủ, Bạn bè, Tin nhắn, Lịch sử, Hồ sơ) + nút tròn "Tạo phòng"; hộp thoại thành toàn màn hình |

Mục tiêu: dùng tốt trên điện thoại bằng trình duyệt (phục vụ các vòng test ở `08-cross-device-testing.md`), đồng thời là nền cho ứng dụng React Native sau này.

## 6. Web người dùng: các màn hình

### 6.1 Đăng nhập / đăng ký / khách (`index.html`)

- Bố cục hai cột trên màn hình rộng: bên trái **khối giới thiệu** (logo, vài dòng mô tả, nền chàm nhạt), bên phải **thẻ biểu mẫu** có tab *Đăng nhập* | *Đăng ký*; dưới cùng liên kết **"Vào bằng tên khách"** (chỉ hiện khi `allow_guest = true`; ẩn đăng ký khi `allow_registration = false`; hiện thông báo khi `maintenance_mode`).
- Dữ liệu cấu hình lấy từ `GET /config/public`. Lỗi hiển thị ngay dưới ô nhập; thông báo chung cho "sai email hoặc mật khẩu" (không lộ email nào tồn tại).
- Đăng ký có thanh đo độ mạnh mật khẩu và hiển thị yêu cầu tối thiểu theo `password_min_length`.

U2 dùng hai tab trên trang xác thực, biểu mẫu tên khách và luồng chuyển thiết bị hiện có. Máy chủ tiếp tục xác thực phiên trước khi phục vụ các trang bên trong, kể cả khi mở liên kết trực tiếp.

### 6.2 Trang chủ

```
┌ Sidebar ┐ ┌──────────────────────────────────────────────────────────────┐
│ ConnectV│ │ Thứ Tư, 18 Tháng 11 · ● Đã kết nối              🔔(2)        │
│ Trang chủ│ │ Xin chào, Mai Linh 👋                [Tham gia bằng mã] [＋ Tạo phòng họp mới]│
│ Phòng họp│ │ Bạn có 1 lời mời gọi, 3 tin nhắn chưa đọc và 1 phòng đang mở.     │
│ Bạn bè ② │ │                                                              │
│ Tin nhắn ③│ │ Đang mở & lời mời                              Xem tất cả →   │
│ Lịch sử  │ │ ┌────────────┐ ┌────────────┐ ┌────────────┐                 │
│ Cài đặt  │ │ │● Đang mở   │ │✉ Lời mời   │ │● Đang mở   │                 │
│          │ │ │Họp nhóm    │ │Từ Minh     │ │Ôn thi DevOps│                 │
│ [Mai Linh]│ │ │(A)(B)(C)+2 │ │"Họp nhóm 2"│ │(A)(B)      │                 │
│          │ │ │[Vào họp ngay]│ │[Từ chối][Tham gia]│[Vào họp ngay]│           │
│          │ │ └────────────┘ └────────────┘ └────────────┘                 │
│          │ │ Lịch sử cuộc gọi gần đây                        Xem tất cả (28) →│
│          │ │ ┌──────────────────────────────────────────────────────────┐ │
│          │ │ │📞 Họp nhóm · 15/11 · 38 phút · 4 người · Chủ trì: Bạn  [Chi tiết][Tải nhật ký chat]│
│          │ │ └──────────────────────────────────────────────────────────┘ │
│          │ │ ● Đã kết nối · 42 ms                        v0.1.0            │
└──────────┘ └──────────────────────────────────────────────────────────────┘
```

- **Câu mô tả** tổng hợp: số lời mời gọi đang chờ (`/invites`), tin nhắn chưa đọc (`/conversations`), phòng đang mở (`/rooms/mine`). Phần nào bằng 0 thì bỏ khỏi câu.
- **Thẻ "Đang mở & lời mời":** thẻ phòng đang mở của tôi (nhãn chính "Đang mở") và thẻ lời mời gọi (nhãn "Lời mời"). Thẻ gồm tiêu đề, người mời hoặc thời điểm bắt đầu, cụm ảnh người tham gia, nút hành động. Khác mockup: **không có giờ lên lịch** vì chưa có tính năng đặt lịch.
- **Lịch sử gần đây:** 5 mục mới nhất từ `/me/call-history`, mỗi dòng có biểu tượng loại (`hosted`/`joined`/`missed_invite`), thông tin phụ và hai hành động *Chi tiết*, *Tải nhật ký chat* (ẩn nếu `chat_available = false`).
- **Nút "Tham gia bằng mã":** hộp thoại nhập mã → `GET /rooms/{code}` (hiện tên phòng, số người, có mật khẩu hay không) → nút *Vào phòng*.
- **Nút "Tạo phòng họp mới":** hộp thoại (tên phòng, mật khẩu tùy chọn, số người tối đa, chế độ) → `POST /rooms` → vào phòng; sau khi vào có thể mời bạn (mục 6.8).
- Trạng thái rỗng thân thiện: chưa có phòng/lịch sử thì hiện lời gợi ý "Tạo phòng đầu tiên" và "Thêm bạn bè".

Trang chủ dùng lối tắt đến `/rooms/join` và `/rooms/create` theo quyết định tách trang. Các thẻ phòng và lời mời dùng dữ liệu thật, tối đa ba thẻ mỗi nhóm. Trang chủ hiển thị năm mục lịch sử mới nhất, mở chi tiết và tải chat nếu có. Luồng chấp nhận lời mời chuyển cùng tab sang màn hình chờ của phòng, giữ ID lời mời trong phiên tab.

### 6.3 Phòng họp

Trang liệt kê **phòng của tôi đang mở** (`/rooms/mine`) dưới dạng thẻ, kèm ô nhập mã để vào phòng người khác. Mỗi thẻ: tên, mã phòng (nút sao chép), số người, nhãn "Có mật khẩu", nút *Vào*, *Mời bạn*, *Đóng phòng* (viền đỏ, có xác nhận). Nhãn **Live** ở sidebar bật khi danh sách này khác rỗng.

### 6.4 Màn hình chờ (lobby) và phòng gọi

**Lobby (trước khi vào):** hai cột: bên trái xem trước camera với thanh đo âm lượng mic và nút bật/tắt; bên phải chọn camera/mic/loa, ô nhập tên (nếu là khách), mật khẩu phòng (nếu cần), nút chính *Vào phòng*. Hiển thị lỗi quyền camera/mic bằng lời dễ hiểu.

U3 hiển thị tên của phiên đã xác thực, kể cả tên đã nhập khi vào bằng khách. Camera và mic mở khi người dùng bấm kiểm tra thiết bị hoặc vào cuộc gọi. Sau khi cấp quyền, có thể chọn camera/mic và chọn loa trên trình duyệt có hỗ trợ. Đối với livestream, camera/mic của người phát vẫn xin quyền khi họ bắt đầu phát. Người có lời mời hợp lệ có thể dùng mã mời thay mật khẩu. Kết nối lại trong thời gian giữ chỗ được kiểm tra theo phiên và lời mời đã dùng cho lượt tham gia đó.

**Phòng gọi (`room.html`):**

```
┌───────────────────────────────────────────────────┬──────────────────┐
│ Họp nhóm · abc-defg-hij [sao chép]   ⏱ 12:41  ●42ms│ [Chat][Người][Mời]│
│ ┌──────────┐ ┌──────────┐                         │ Mai Linh: chào…  │
│ │  Bạn     │ │  Minh 🎤✕│     lưới video           │ Minh: ok         │
│ └──────────┘ └──────────┘     tự co theo số người  │                  │
│ ┌──────────┐ ┌──────────┐                         │ [Nhập tin nhắn…] │
│ │  An ✋    │ │  Linh    │                         │                  │
│ └──────────┘ └──────────┘                         │                  │
├───────────────────────────────────────────────────┴──────────────────┤
│        [🎤] [📷] [🖥 Chia sẻ] [✋] [👥 Mời bạn] [💬] [📞 Rời phòng]   │
└──────────────────────────────────────────────────────────────────────┘
```

- Thanh điều khiển dưới đáy; nút **Rời phòng** màu đỏ ở cuối.
- Khung bên phải có 3 tab: **Chat** (chat trong phòng), **Người** (danh sách người trong phòng, host có menu *Tắt mic / Mời ra khỏi phòng*), **Mời** (mục 6.8).
- Chỉ số mạng (RTT, mất gói, bitrate, loại kết nối `host/srflx/relay`) hiển thị ở **bong bóng nhỏ** cạnh đồng hồ; bấm vào mở bảng chi tiết (kèm nút *Sao chép báo cáo*, `08-cross-device-testing.md` mục 3.4).
- Lưới video: 1 người toàn khung, 2 người song song, 3-4 người lưới 2×2; người đang nói có viền nhấn (từ mức âm thanh `getStats`); chia sẻ màn hình chiếm vùng lớn, các video nhỏ xếp dải bên cạnh.
- Trên điện thoại: khung bên phải thành **ngăn kéo từ dưới lên**.

### 6.5 Bạn bè (E2)

```
┌──────────────────────────────────────────────────────────────┐
│ Bạn bè                                                       │
│ [Tìm bạn bằng email: ______________________ ] [Tìm]          │
│  ┌──────────────────────────────────────────────┐            │
│  │ (MA) Mai Linh   · Chưa là bạn      [Kết bạn]  │ ← kết quả  │
│  └──────────────────────────────────────────────┘            │
│ [Bạn bè (24)] [Lời mời (2)] [Đã chặn (0)]                    │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ (An)● Nguyễn An        Trực tuyến     [💬][📞 Gọi][⋯]      │ │
│ │ (Bi)  Trần Bình        Ngoại tuyến    [💬][📞 Gọi][⋯]      │ │
│ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

- **Tìm bằng email:** bắt buộc nhập đủ địa chỉ; kết quả là **một thẻ** hoặc thông báo trung tính **"Không tìm thấy người dùng phù hợp"** (dùng cho cả "không có" lẫn "đang ẩn"). Nút tương ứng với `relationship`: *Kết bạn*, *Đã gửi lời mời* (vô hiệu, có *Hủy*), *Chấp nhận / Từ chối*, hoặc nhãn *Bạn bè*.
- **Tab Lời mời:** hai khối "Đã nhận" (nút *Chấp nhận*, *Từ chối*) và "Đã gửi" (nút *Hủy*). Từ chối không có thông báo cho người gửi (đã quyết định ở D27), giao diện không hứa là "đã báo cho họ".
- **Hàng bạn bè:** ảnh đại diện có chấm trực tuyến (xanh), tên, trạng thái chữ; nút **Nhắn tin**, **Gọi** (tạo phòng nhanh và mời người đó, `extend.md` mục 8.3.1), menu `⋯`: *Hủy kết bạn*, *Chặn* (đều có hộp thoại xác nhận). Trạng thái online ẩn nếu người kia tắt `show_online_status`.
- **Tab Đã chặn:** danh sách kèm nút *Bỏ chặn*.
- Giới hạn: khi đạt `max_friends_per_user`, nút *Kết bạn* báo lý do rõ ràng.

### 6.6 Tin nhắn (E4)

```
┌───────────────────────┬──────────────────────────────────────────┐
│ Tin nhắn              │ (An)● Nguyễn An            [📞 Mời vào phòng] │
│ [Tìm cuộc trò chuyện] │──────────────────────────────────────────│
│ (An)● Nguyễn An   ③   │            Hôm nay                        │
│  "Mai họp lúc 9h nhé" │ (An) Mai họp lúc 9h nhé        09:12      │
│ (Bi)  Trần Bình       │                  OK, mình vào nhé ✓✓ 09:14│
│  "ok"                 │                                          │
│                       │ [Nhập tin nhắn…                  ] [Gửi]  │
└───────────────────────┴──────────────────────────────────────────┘
```

- Hai ngăn: danh sách cuộc trò chuyện (sắp theo tin mới nhất, nhãn số tin chưa đọc) và khung chat. Trên điện thoại hiển thị **từng ngăn một** (danh sách → mở chat → nút quay lại).
- Tin của mình căn phải màu chính; của bạn căn trái màu trung tính; có **dấu thời gian** theo nhóm ngày; trạng thái *đã gửi / đã xem* (`dm_read`).
- **Chỉ báo "đang nhập…"** (`dm_typing`) hiện ở đầu khung nhập.
- Tin chỉ hiển thị dạng **văn bản thuần** (dùng `textContent`), xuống dòng được giữ nguyên.
- Xóa tin của mình qua menu bấm giữ/chuột phải; tin đã xóa hiển thị "Tin nhắn đã bị xóa".
- Khi không còn là bạn hoặc bị chặn: ô nhập bị thay bằng dòng "Bạn không thể nhắn tin cho người này nữa" (lịch sử vẫn xem được).
- Nút **"Mời vào phòng"** ở đầu khung: tạo phòng nhanh và mời người này.
- Khi nối lại mạng: tự tải phần tin bị lỡ (`after=<id>`).

### 6.7 Thông báo và lời mời gọi

**Chuông thông báo** (thanh trên): danh sách gộp *lời mời kết bạn*, *lời mời gọi đang chờ*, *lời mời gọi đã lỡ*; số đỏ là số chưa xử lý; bấm vào mục thì đi đến màn hình tương ứng.

**Thẻ lời mời gọi (nổi, mọi màn hình):**

```
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  (Mi) Minh mời bạn vào "Họp nhóm"
  🔒 Phòng có mật khẩu (không cần nhập)
  Hết hạn sau 8:42
  [Từ chối]            [Tham gia]
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```

- Xuất hiện góc trên bên phải, có **đếm ngược** theo `expires_at`; hết hạn tự đóng và chuyển vào "đã lỡ".
- *Tham gia* → mở phòng với `invite_id`; *Từ chối* → `POST /invites/{id}/decline`.
- Âm báo (tùy chọn, bật/tắt ở Cài đặt): trình duyệt có thể chặn phát âm thanh khi người dùng chưa từng tương tác với trang; ⚠ cần kiểm tra khi làm.
- Có `aria-live` để trình đọc màn hình đọc được lời mời (mục 10).
- Khi ứng dụng **không mở** thì không có thông báo (thông báo đẩy để `idea.md`).

### 6.8 Mời bạn vào cuộc gọi (E5)

Hộp thoại (hoặc tab **Mời** ở khung bên phải của phòng):

- Ô tìm nhanh theo tên; danh sách bạn bè **trực tuyến lên trước**, mỗi hàng có hộp kiểm và trạng thái (*Đã mời*, *Đã tham gia*, *Đã từ chối*).
- Nút chính *Mời (n)* (tối đa 20 người một lần); kết quả hiển thị theo `skipped[].reason` bằng lời tiếng Việt ("không phải bạn bè", "đã ở trong phòng", "đã được mời").
- Nút phụ *Sao chép mã phòng* (người không phải bạn bè vẫn vào được bằng mã).

### 6.9 Lịch sử cuộc gọi (E6)

- Thanh lọc: *Tất cả / Đã chủ trì / Đã tham gia / Lỡ lời mời*, chọn khoảng ngày.
- Danh sách dòng như ở Trang chủ (mục 6.2) nhưng đầy đủ, có phân trang. Mỗi dòng: biểu tượng loại, tên phòng, ngày giờ, thời lượng, số người, cụm ảnh người tham gia.
- **Ngăn chi tiết (drawer)** bên phải: tên và mã phòng, mốc bắt đầu/kết thúc, danh sách người tham gia với giờ vào/ra và lý do rời, nút **Tải nhật ký chat** (nếu còn), nút *Tạo phòng mới với những người này* (ý tưởng, không làm ở bản đầu).
- Nút **Xóa lịch sử của tôi** (xác nhận hai bước) → `DELETE /me/call-history`.
- Mục chat đã quá thời hạn lưu: nút bị vô hiệu kèm chú thích "Nhật ký chat đã hết hạn lưu".

### 6.10 Hồ sơ và cài đặt (E1)

Trang Cài đặt có tab dọc: **Hồ sơ**, **Bảo mật**, **Quyền riêng tư**, **Giao diện**, (**Thiết bị**: camera/mic mặc định, tùy chọn).

- **Hồ sơ:** khối ảnh đại diện lớn (96 px) với nút *Tải ảnh lên* (xem trước, báo lỗi `INVALID_IMAGE`/`IMAGE_TOO_LARGE` bằng lời dễ hiểu), *Gỡ ảnh*; ô **Họ và tên**, **Ngày sinh** (chọn ngày, có thể để trống), **Email** (chỉ đọc, ghi chú "Liên hệ quản trị viên nếu cần đổi"); nút *Lưu thay đổi* chỉ bật khi có thay đổi.
- **Bảo mật:** biểu mẫu đổi mật khẩu (mật khẩu hiện tại, mới, nhập lại, thanh đo độ mạnh); nút *Đăng xuất khỏi mọi thiết bị* (`/auth/logout-all`); nhắc rằng đổi mật khẩu sẽ đăng xuất các phiên khác.
- **Quyền riêng tư:** công tắc *Cho phép người khác tìm tôi bằng email*, *Hiển thị trạng thái trực tuyến cho bạn bè*, kèm một câu giải thích mỗi mục.
- **Giao diện:** *Sáng / Tối / Theo hệ thống*, bật/tắt âm báo lời mời.

## 7. Trang quản trị

### 7.1 Khung giao diện admin

- Nền **tối** mặc định, dùng chung bộ token ở mục 3 (chủ đề `dark`).
- Sidebar: logo + nhãn **ADMIN**; menu *Tổng quan*, *Phòng họp trực tiếp* (số phòng đang mở), *Thành viên*, *Báo cáo & Phân tích*, *Cấu hình & Bảo mật*; thẻ quản trị viên ở đáy (tên, "Quản trị viên", nút đăng xuất).
- Thanh trên: tiêu đề trang, **nhãn trạng thái hệ thống**, các nút hành động của trang.
- Cập nhật dữ liệu sống bằng **HTMX** (`hx-trigger="every 5s"`) cho thẻ chỉ số và bảng phòng; không cần WebSocket riêng cho admin.
- Bảo vệ: giữ nguyên các quy tắc đã chốt (cookie phiên, CSRF, cổng riêng tư, `/admin` bị chặn ở cổng công khai).

### 7.2 Tổng quan hệ thống

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Tổng quan hệ thống   ● Hệ thống hoạt động bình thường  [Xuất báo cáo][＋ Tạo phòng họp]│
│ ┌ PHÒNG ĐANG CHẠY ┐ ┌ BĂNG THÔNG TURN  ┐ ┌ TỶ LỆ VÀO PHÒNG THÀNH CÔNG ┐ │
│ │ 12              │ │ 38 / 100 Mbps    │ │ 99,4 %                    │ │
│ │ 41 người        │ │ ▓▓▓▓░░░░░░  38 % │ │ 24 giờ qua                │ │
│ └─────────────────┘ └──────────────────┘ └───────────────────────────┘ │
│ Các phòng họp đang diễn ra                              [● Thời gian thực]│
│ TÊN PHÒNG / CHỦ TRÌ   SỐ NGƯỜI   THỜI LƯỢNG   BẢO MẬT   THAO TÁC         │
│ Họp nhóm              4          00:38        🔒 Mật khẩu [Chi tiết][Ngắt phòng]│
│  Chủ trì: Mai Linh                                                        │
│ Ôn thi DevOps         3          00:12        Công khai   [Chi tiết][Ngắt phòng]│
└──────────────────────────────────────────────────────────────────────────┘
```

Nội dung ba thẻ chỉ số (khác mockup vì dữ liệu thật của dự án):

| Mockup | Bản này | Nguồn |
|---|---|---|
| Phòng họp đang chạy (số lớn, % thay đổi) | **Phòng đang chạy** + tổng số người đang trong phòng | `/admin/dashboard` (RAM); phần "so với hôm qua" chỉ có khi có Prometheus |
| Băng thông số (Gbps, % công suất) | **Băng thông TURN ước tính** (Mbps, trung bình 5 phút từ bộ đếm phiên đã kết thúc) | Metric coturn qua Prometheus (`PROMETHEUS_URL`); ngưỡng tùy chọn `TURN_CAPACITY_MBPS`. Khi thiếu dữ liệu, thẻ hiện `—`. |
| Độ ổn định QoS (99,98%) | **Tỷ lệ vào phòng thành công** trong 24 giờ | `room_joins_total` chia cho `join_room_duration_seconds_count`; QoS từ RTT và mất gói vẫn ở `idea.md`. |

Bảng phòng: cột *Băng thông* và *Trạng thái E2E* của mockup được thay bằng **Thời lượng** và **Bảo mật (có mật khẩu/công khai)**, vì hệ thống không có dữ liệu băng thông theo phòng và chưa có mã hóa đầu cuối (xem `idea.md`). *Chi tiết* mở ngăn kéo (người tham gia, host, mốc vào phòng); *Ngắt phòng* mở hộp thoại xác nhận rồi gọi `DELETE /admin/rooms/{code}` (ghi audit).

### 7.3 Các trang còn lại của admin

| Trang | Nội dung | API (đã có hoặc từ `extend.md`) |
|---|---|---|
| **Phòng họp trực tiếp** | Bảng đầy đủ + lọc, tự làm mới; nút *Chi tiết*, *Kick*, *Ngắt phòng* | `/admin/rooms` |
| **Thành viên** | Bảng: ảnh, họ tên, email, vai trò, trạng thái, lần đăng nhập gần nhất; tìm kiếm, lọc, phân trang; ngăn kéo chi tiết (ngày sinh, số bạn, số cuộc gọi, phiên đang hoạt động) với hành động *Khóa/Mở khóa*, *Đổi vai trò*, *Reset mật khẩu*, *Buộc đăng xuất*, *Gỡ ảnh đại diện*, *Xóa* (đều có xác nhận và audit) | `/admin/users*`, `extend.md` mục 11 |
| **Báo cáo & Phân tích** | Biểu đồ đường/cột: người dùng mới theo ngày, số cuộc gọi và tổng phút gọi theo ngày, giờ cao điểm; nút *Xuất CSV*; bảng lịch sử cuộc gọi đã kết thúc | `/admin/dashboard`, `/admin/call-history` |
| **Cấu hình & Bảo mật** | Tab **Cấu hình** (nhóm: Truy cập, Phòng và chat, Media, TURN, Bảo mật, **Bạn bè & tin nhắn**, **Lịch sử & ảnh đại diện**; mỗi mục có mô tả, giá trị mặc định, nút *Khôi phục mặc định*, xác nhận khi lưu), tab **Audit log** (lọc theo admin/hành động/ngày) | `/admin/settings`, `/admin/audit-logs` |

Biểu đồ vẽ bằng **SVG do server tạo** (đường sparkline và cột đơn giản), không cần thư viện biểu đồ phía client, hợp với quy tắc CSP chặt và máy yếu.

Bảng và biểu mẫu dùng thành phần ở mục 4; thao tác nguy hiểm luôn qua hộp thoại xác nhận có nêu rõ đối tượng ("Ngắt phòng *Họp nhóm* đang có 4 người?").

## 8. Ánh xạ mockup sang dự án

Trạng thái: **Có** = làm được với backend hiện có; **Cần Ex** = phụ thuộc bước của `extend.md`; **Ý tưởng** = chưa có backend, ghi ở `idea.md`.

### 8.1 Giao diện người dùng

| Thành phần trong mockup | Hiển thị ở bản này | Trạng thái |
|---|---|---|
| Logo ConnectV + "Workspace" | Tên ứng dụng lấy từ một hằng số cấu hình client | Có |
| Menu: Trang chủ | Trang chủ | Có |
| Menu: Phòng họp + nhãn Live | Phòng của tôi, nhãn Live khi có phòng đang mở | Có |
| Menu: Lịch họp (số) | **Ẩn** ở bản đầu | Ý tưởng I-01 |
| Menu: Biên bản họp | Thay bằng **Lịch sử** | Cần E6 |
| Menu: Cài đặt | Hồ sơ và cài đặt | Cần E1 |
| (thêm) Bạn bè, Tin nhắn | Mục menu mới | Cần E2, E4 |
| Ngày + "Hệ thống sẵn sàng" | Ngày hiện tại + trạng thái kết nối | Có |
| "Xin chào, {tên} 👋" | Họ tên từ `/me` | Có |
| "Hôm nay bạn có N cuộc họp sắp diễn ra…" | Lời mời gọi, tin chưa đọc, phòng đang mở | Cần E4, E5 |
| Nút "Tham gia bằng mã" | Hộp thoại nhập mã | Có |
| Nút "Tạo phòng họp mới" | Hộp thoại tạo phòng | Có |
| "Cuộc họp hôm nay" (giờ, mô tả) | "Đang mở & lời mời" (không có giờ lên lịch) | Có / Cần E5 |
| Liên kết "Xem lịch" | Bỏ | Ý tưởng I-01 |
| "Biên bản & Lịch sử gần đây" | Lịch sử cuộc gọi gần đây | Cần E6 |
| Nút "Xem bản ghi" | Không có (cần ghi hình) | Ý tưởng I-03 |
| Nút "Tải Transcript" | **Tải nhật ký chat** (không phải transcript giọng nói) | Cần E6; transcript là I-04 |
| Chân trang "Đã kết nối máy chủ…" | Trạng thái Socket.io + độ trễ + phiên bản | Có |
| Chức danh dưới tên ("Product Manager") | Hiển thị email | Chức danh là ý tưởng I-17 |

### 8.2 Giao diện quản trị

| Thành phần trong mockup | Hiển thị ở bản này | Trạng thái |
|---|---|---|
| Logo + ADMIN, menu 5 mục | Giữ cấu trúc, đổi nhãn theo mục 7.1 | Có |
| Nhãn "Hệ thống hoạt động bình thường" | Từ `/ready` (DB) và kiểm tra các dịch vụ chính; đổi màu cam/đỏ khi có sự cố | Có |
| Nút "Xuất báo cáo" | Xuất CSV (người dùng mới, cuộc gọi theo ngày) | Có (A6) / Cần E7 |
| Nút "Tạo phòng họp" | Admin tạo phòng với tư cách chủ phòng | Có |
| Thẻ "Phòng họp đang chạy" | Số phòng + số người; phần trăm thay đổi cần Prometheus | Có / một phần |
| Thẻ "Băng thông số (Gbps)" | **Băng thông TURN** (Mbps) | Cần Prometheus |
| Thẻ "Độ ổn định QoS" | **Tỷ lệ vào phòng thành công** | Có (metric); QoS thật là ý tưởng I-06 |
| Bảng phòng: tên/chủ trì, số người | Giữ nguyên | Có |
| Cột "Băng thông" | **Thời lượng** | Có |
| Cột "Trạng thái E2E" | **Bảo mật** (mật khẩu/công khai) | Có; E2E là ý tưởng I-10 |
| Nút "Chi tiết", "Ngắt phòng" | Giữ nguyên (có xác nhận, audit) | Có |
| Thẻ quản trị viên ("Super Admin") | Tên + "Quản trị viên" + đăng xuất (chưa có vai trò phân cấp) | Có |
| Quy mô số liệu (hàng nghìn phòng, Gbps) | Số liệu thật của hệ thống, nhỏ hơn nhiều; định dạng số tự đổi đơn vị | Có |

## 9. Cách thực hiện

### 9.1 Cấu trúc thư mục client (không cần build)

```
client/
├── index.html            # đăng nhập / đăng ký / khách
├── app.html              # khung ứng dụng (sidebar + màn hình)
├── room.html             # phòng gọi
├── styleguide.html       # trang xem thử thành phần (chỉ dev)
├── css/
│   ├── tokens.css        # biến màu, chữ, khoảng cách (nguồn sự thật duy nhất)
│   ├── base.css          # reset, chữ, trạng thái focus
│   ├── components.css    # nút, thẻ, chip, bảng, modal...
│   ├── app.css           # bố cục khung ứng dụng, các màn hình
│   └── room.css          # bố cục phòng gọi
├── fonts/                # Inter (woff2), tự lưu
├── icons/sprite.svg
└── js/
    ├── api.js, socket.js, webrtc.js, stats.js, ui.js     # đã có
    └── app/
        ├── router.js     # định tuyến theo hash, nạp màn hình theo nhu cầu
        ├── store.js      # trạng thái dùng chung (số lời mời, tin chưa đọc, trạng thái online)
        ├── i18n/vi.js    # toàn bộ chuỗi giao diện (chuẩn bị cho en)
        ├── components/   # avatar, toast, modal, drawer, tabs, dropdown...
        └── pages/        # home, rooms, friends, messages, history, settings
```

### 9.2 Quy tắc code giao diện

- **Không framework, không bước build** (D21 giữ nguyên): ES modules, nạp màn hình bằng `import()` khi cần.
- **Một nguồn màu:** chỉ `tokens.css` chứa giá trị màu; các tệp khác dùng `var(--...)`.
- **Chuỗi giao diện** ở `i18n/vi.js`, không ghi cứng trong HTML/JS; chuẩn bị mở rộng ngôn ngữ.
- **Dữ liệu người dùng luôn gán bằng `textContent`**, không dùng `innerHTML` (tên, tin nhắn, tên phòng đều là đầu vào không tin cậy).
- **Store** nhỏ kiểu phát/nhận sự kiện; các sự kiện Socket.io cập nhật store, màn hình và nhãn số tự vẽ lại.
- **Mất kết nối:** hiển thị dải thông báo "Đang kết nối lại…", khi nối lại gọi các API đồng bộ ở `extend.md` mục 6.
- **Hiệu năng:** ảnh đại diện dùng bản 64 px trong danh sách, 256 px ở hồ sơ; ảnh tải lười (`loading="lazy"`); không thư viện lớn phía client.

### 9.3 Trang admin

- Giữ **Jinja2 + HTMX** (D17), thêm mẫu `base_admin.html` dùng chung `tokens.css` với chủ đề tối (app phục vụ thư mục `client/css` để dùng lại).
- Các mẫu: `dashboard.html`, `live_rooms.html`, `users.html`, `reports.html`, `settings.html`, `audit.html`, cùng thư mục `partials/` cho các phần HTMX cập nhật riêng (thẻ chỉ số, hàng bảng).
- **HTMX được lưu cục bộ** (không nạp từ CDN) để chặt chẽ với CSP: `script-src 'self'`, `img-src 'self' data:`, `font-src 'self'`.
- Cập nhật sống bằng `hx-trigger="every 5s"`; biểu đồ là SVG do server dựng.

## 10. Khả năng tiếp cận và chất lượng

| Hạng mục | Yêu cầu |
|---|---|
| Bàn phím | Mọi thao tác dùng được bằng bàn phím; thứ tự Tab hợp lý; hộp thoại khóa focus và đóng bằng `Esc` |
| Tương phản | Chữ thường ≥ 4,5:1, chữ lớn và thành phần giao diện ≥ 3:1 ở cả hai chủ đề |
| Không chỉ dùng màu | Trạng thái luôn kèm chữ hoặc biểu tượng |
| Trình đọc màn hình | Thẻ lời mời gọi dùng vùng thông báo (`role="alertdialog"` hoặc `aria-live`); nút chỉ có biểu tượng có nhãn (`aria-label`) |
| Giảm chuyển động | Tắt hoạt ảnh khi `prefers-reduced-motion` |
| Vùng chạm | Tối thiểu khoảng 40-44 px trên điện thoại |
| Tiếng Việt | Kiểm tra cắt chữ và xuống dòng với chuỗi dài; không cắt giữa dấu |
| Trạng thái | Mỗi danh sách có đủ: đang tải (skeleton), rỗng, lỗi (có nút thử lại) |
| Trình duyệt | Theo ma trận ở `08-cross-device-testing.md` mục 4 (kể cả Safari trên iPhone) |

Mục tiêu tham khảo: điểm Lighthouse mục Accessibility ≥ 90 cho các màn hình chính. Đây là **mục tiêu**, không phải cam kết; ghi lại số đo thật vào báo cáo.

## 11. Lộ trình

| Bước | Nội dung | Làm sau |
|---|---|---|
| **U1** | `tokens.css`, `base.css`, `components.css`, sprite biểu tượng, trang `styleguide.html` | A1 (có thể làm song song với A2-A4) |
| **U2** | `index.html` (đăng nhập/đăng ký/khách), Trang chủ, Phòng của tôi, Vào/Tạo phòng trên URL riêng | A2, A4, U1 |
| **U3** | Lobby và phòng gọi theo phong cách mới | A5 (A9 cho lưới nhóm), U1 |
| **U4** | Trang admin: khung, Tổng quan, Phòng trực tiếp, Thành viên, Cấu hình & Bảo mật | A6, U1 |
| **U5** | Bạn bè, Tin nhắn, Lời mời gọi, Mời bạn vào phòng | E2, E3, E4, E5, U2 |
| **U6** | Lịch sử, Hồ sơ và cài đặt; admin Báo cáo & Phân tích | E1, E6, E7, U2, U4 |
| **U7** | Đáp ứng kích thước màn hình, tiếp cận, kiểm tra trực quan, chỉnh sửa cuối | U2-U6 |

Thứ tự đề xuất: **U1 → U2 → U3 → U4**, rồi U5/U6 khi các bước E tương ứng xong, cuối cùng U7. U1 và U2 mang lại thay đổi nhìn thấy sớm nhất mà không phụ thuộc E.

**Điều kiện hoàn thành mỗi bước:** màn hình chạy được trên hai trình duyệt khác nhau ở ba cỡ màn hình (rộng, vừa, điện thoại); không có lỗi trong console; qua kiểm tra bàn phím; ảnh chụp màn hình đính kèm báo cáo của bước.

Kết quả triển khai và nghiệm thu ở [báo cáo U2/U3](u2-u3-report.md) và [báo cáo U4–U7](u4-u7-report.md). Hai web dùng URL riêng. Các màn hình Bạn bè, Tin nhắn, Lịch sử và Hồ sơ của web người dùng lần lượt ở `/friends`, `/messages`, `/history` và `/account`. Báo cáo quản trị ở `/admin/reports`.

## 12. Tài liệu khác cần cập nhật

| File | Cập nhật |
|---|---|
| `docs/README.md` | Thêm mục giao diện, lộ trình U1-U7, nhắc `docs_v3/` |
| `docs/04-settings.md` | Biến môi trường `TURN_CAPACITY_MBPS` (và nhắc `PROMETHEUS_URL` cần cho thẻ băng thông) |
| `docs/05-deployment.md` | Phục vụ `client/` (kể cả phông và biểu tượng) và quy tắc CSP của trang admin |
| `docs/06-decisions.md` | D33-D36 ở mục 13 |
| `docs/08-cross-device-testing.md` | Thêm kiểm tra giao diện trên điện thoại (cỡ màn hình, thanh điều hướng dưới đáy) |
| `AGENT_PROMPT.md` | Thêm câu lệnh U1-U7 (mục 14); giữ quy tắc "không React/Vue cho `client/`" |
| `docs_v3/extend.md` | Đã tham chiếu; thêm `/config/public` các khóa giao diện nếu cần |

## 13. Quyết định mới và câu hỏi còn mở

| ID | Quyết định (đề xuất) | Lý do |
|---|---|---|
| D33 | Giữ **JS thuần + CSS tokens**, không thêm framework UI dù giao diện phong phú hơn | Đã chốt D21; giao diện thuộc loại thẻ, bảng, biểu mẫu nên không cần framework; tránh bước build |
| D34 | **Mockup là hướng thị giác**, phần chưa có dữ liệu thì đổi nội dung hoặc ẩn, không làm giả số liệu | Giao diện không được hứa điều hệ thống không làm được; tránh số liệu bịa trong báo cáo |
| D35 | Admin và người dùng **dùng chung `tokens.css`**; admin tối mặc định, người dùng sáng mặc định | Đồng nhất thương hiệu, bảo trì một nơi |
| D36 | Menu bản đầu: Trang chủ, Phòng họp, Bạn bè, Tin nhắn, Lịch sử, Cài đặt; mục chưa sẵn sàng **ẩn** | Không để mục không hoạt động |

| # | Câu hỏi | Đề xuất | Cần chốt trước |
|---|---|---|---|
| Q18 | **ĐÃ CHỐT: Videocall** (người dùng xác nhận 18/11/2026). | Hằng `productName` trong `client/js/app/i18n/vi.js` | U1 |
| Q19 | **[CẦN CHỐT]** Có làm "Lịch họp" (đặt lịch, lời nhắc) ở bản này không? Mockup có nhưng chưa có backend | Không; để `idea.md` I-01 | U2 |
| Q20 | Phòng gọi mở cùng tab hay tab mới? | Cùng tab (đơn giản, cuộc gọi chiếm toàn màn hình) | U3 |
| Q21 | Giao diện người dùng có cần chủ đề tối ngay từ đầu? | Có, vì dùng token nên chi phí thấp | U1 |
| Q22 | Có dùng emoji trong giao diện (như "👋" ở lời chào)? | Có, tùy chọn tắt ở chủ đề trang trọng | U2 |

## 14. Câu lệnh gợi ý cho agent (bổ sung phần 2 của `AGENT_PROMPT.md`)

| Bước | Câu lệnh |
|---|---|
| U1 | `Thực hiện bước U1 theo docs_v3/ui.md mục 3, 4, 9.1: tokens.css (hai chủ đề), base.css, components.css, sprite biểu tượng, styleguide.html. Không framework, không build. Trình bày kế hoạch trước và chốt bảng màu bằng cách đối chiếu ảnh mockup.` |
| U2 | `Thực hiện bước U2 theo ui.md mục 5, 6.1-6.3: index.html và các trang riêng Trang chủ, Phòng của tôi, Vào/Tạo phòng. Dùng textContent cho dữ liệu người dùng. Trình bày kế hoạch trước.` |
| U3 | `Thực hiện bước U3 theo ui.md mục 6.4: restyle lobby và room.html, lưới video, thanh điều khiển, khung bên phải 3 tab, bong bóng chỉ số mạng. Trình bày kế hoạch trước.` |
| U4 | `Thực hiện bước U4 theo ui.md mục 7: base_admin.html dùng chung tokens.css, Tổng quan, Phòng trực tiếp, Thành viên, Cấu hình & Bảo mật với HTMX cập nhật 5 giây, CSP chặt, HTMX lưu cục bộ. Trình bày kế hoạch trước.` |
| U5 | `Thực hiện bước U5 theo ui.md mục 6.5-6.8: Bạn bè, Tin nhắn, thẻ lời mời gọi, hộp thoại mời bạn; kết nối sự kiện socket vào store. Chỉ làm khi E2-E5 đã xong. Trình bày kế hoạch trước.` |
| U6 | `Thực hiện bước U6 theo ui.md mục 6.9-6.10 và 7.3: Lịch sử, Hồ sơ và cài đặt, admin Báo cáo & Phân tích với SVG do server dựng. Trình bày kế hoạch trước.` |
| U7 | `Thực hiện bước U7 theo ui.md mục 5.4 và 10: đáp ứng kích thước, tiếp cận, kiểm tra bàn phím và tương phản, báo cáo điểm Lighthouse thật. Trình bày kế hoạch trước.` |
