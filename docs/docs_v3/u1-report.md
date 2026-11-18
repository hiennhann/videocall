# U1 — Nền tảng giao diện Videocall V3

Ngày kiểm tra: **18/11/2026**. Nhánh: **`feat/update-ui-v3`**.

## Phạm vi đã thực hiện

Triển khai **giai đoạn 1 / U1** của `agent_prompt_v3_md.md`, theo `ui.md` mục 3, 4 và 9.1. Tên sản phẩm giữ **Videocall** theo xác nhận của người dùng.

| Tệp | Nội dung |
|---|---|
| `client/css/tokens.css` | Hai chủ đề, màu chữ/trạng thái/focus, chữ, khoảng cách, bo góc, bóng, thời gian chuyển động |
| `client/css/base.css` | Inter cục bộ, kiểu chữ, focus, liên kết bỏ qua điều hướng, giảm chuyển động |
| `client/css/components.css` | Nút, ô nhập/chọn, switch/checkbox, badge, card, avatar, menu, bảng, tab, modal/drawer, toast, dropdown, progress, empty state, skeleton |
| `client/icons/sprite.svg` | 18 biểu tượng SVG nét, kích thước hiển thị 20 px, dùng `currentColor` |
| `client/fonts/InterVariable.woff2`, `LICENSE.txt` | Inter variable 100–900, giấy phép SIL OFL 1.1 |
| `client/js/app/i18n/vi.js` | Tên sản phẩm và chuỗi tiếng Việt cho thành phần mẫu |
| `client/js/app/components/primitives.js` | Avatar sinh màu theo ID, tab có phím mũi tên/Home/End, dialog, dropdown |
| `client/styleguide.html`, `client/js/styleguide.js`, `client/css/styleguide.css` | Trang thử các biến thể, trạng thái, giao diện sáng/tối/theo hệ thống |
| `backend/app/api/client.py`, `backend/app/main.py` | Phục vụ trang mẫu khi `ENV=dev`, trả 404 ở môi trường khác; chặn cả truy cập trực tiếp qua static |
| `tools/check-ui-u1.cjs`, `backend/tests/unit/test_client.py` | Kiểm tra trình duyệt và việc giới hạn trang mẫu ở môi trường dev |

Các ví dụ trên trang được ghi rõ là dữ liệu mẫu. Chỉ số chưa có nguồn dùng dấu `—`. Thao tác tạo/xóa/nhận lời mời chỉ thử thành phần, không gọi API nghiệp vụ. Các trang V2 tiếp tục dùng CSS hiện tại cho tới U2–U4. U1 không thêm migration, API nghiệp vụ hay ứng dụng mobile.

## Cách mở để duyệt

Với `.env` hiện có đặt `ENV=dev`, chạy tại thư mục gốc:

```powershell
docker compose up --build --wait
```

Mở **<http://localhost:8000/styleguide>**. Có thể dùng `/client/styleguide.html` trong cùng môi trường dev. Việc mở tệp HTML trực tiếp từ ổ đĩa không thay thế máy chủ vì ES modules, phông và sprite dùng đường dẫn cùng nguồn.

Dùng lựa chọn **Giao diện** ở đầu trang để thử Sáng/Tối/Theo hệ thống. Lựa chọn được lưu bằng khóa riêng `videocall.styleguide.theme`, không sửa lựa chọn chủ đề của giao diện V2.

## Kết quả kiểm tra

Kiểm tra tự động bằng Playwright 1.65.1 trên trình duyệt cài sẵn, chế độ headless. Mỗi trình duyệt chạy cả **sáng và tối** ở **1440, 900, 390 px**, tổng cộng **12 tổ hợp**. Chiều cao viewport 1000 px; ảnh chụp toàn trang.

| Trình duyệt | Phiên bản | 1440 px | 900 px | 390 px |
|---|---|---|---|---|
| Chrome | 157.0.8103.79 | Đạt cả hai chủ đề | Đạt cả hai chủ đề | Đạt cả hai chủ đề |
| Edge | 157.0.4341.60 | Đạt cả hai chủ đề | Đạt cả hai chủ đề | Đạt cả hai chủ đề |

- Không lỗi console, JavaScript, tải tài nguyên hay CSP. Không tải tài nguyên bên ngoài.
- Không cuộn ngang toàn trang; bảng và thanh mục trên màn hình hẹp cuộn trong vùng riêng.
- Modal/drawer mở bằng Enter, giữ Tab và Shift+Tab bên trong, Esc đóng và trả focus đúng nút mở. Dùng hành vi native của `dialog.showModal()` và vòng Tab tường minh.
- Tab hỗ trợ mũi tên, Home, End và cập nhật `aria-selected`/`tabindex`. Dropdown đóng bằng Esc và trả focus về nút mở.
- Gửi tên phòng trống hiện lỗi và focus ô nhập; nhập hợp lệ bỏ lỗi. Chuỗi chứa thẻ HTML không được chèn thành markup.
- Lời mời mẫu nhận/từ chối được; đồng hồ 30 giây được kiểm tra hết hạn bằng đồng hồ mô phỏng, sau đó vô hiệu nút nhận.
- Chủ đề theo hệ thống cập nhật khi hệ điều hành thay đổi; lựa chọn giữ lại sau tải lại. `prefers-reduced-motion` tắt animation.
- Unit test backend: **6 passed**. Ruff lint và format: đạt.

### Tương phản

Đo từ giá trị CSS thực tế bằng công thức độ chói tương đối sRGB; 21 cặp cho mỗi chủ đề. Chữ thường yêu cầu ≥ 4,5:1; viền/focus/thanh tiến độ yêu cầu ≥ 3:1. [Kết quả đầy đủ](assets/u1/checks.json).

| Cặp màu | Sáng | Tối |
|---|---:|---:|
| Chữ chính / thẻ | 17,85:1 | 14,33:1 |
| Chữ phụ / nền ứng dụng | 5,67:1 | 8,54:1 |
| Chữ nút chính / nền nút | 6,29:1 | 5,12:1 |
| Chữ nút chính / nền hover | 7,90:1 | 4,65:1 |
| Thành công / nền trạng thái | 6,49:1 | 8,48:1 |
| Cảnh báo / nền trạng thái | 6,37:1 | 8,51:1 |
| Nguy hiểm / nền trạng thái | 5,30:1 | 7,77:1 |
| Viền ô nhập / thẻ | 3,82:1 | 4,60:1 |
| Thanh tiến độ / nền thanh | 5,14:1 | 3,26:1 |

Không coi viền phân cách trang trí hoặc thành phần vô hiệu là chữ/điều khiển đang hoạt động. Đây là kiểm tra bộ thành phần U1, chưa phải kiểm toán khả năng tiếp cận cho toàn bộ ứng dụng.

### Phông chữ và tài nguyên

Inter **4.001** (`git-9221beed3`), WOFF2 **352.240 byte**, tải từ [dự án Inter](https://rsms.me/inter/font-files/InterVariable.woff2); [giấy phép gốc](https://github.com/rsms/inter/blob/master/LICENSE.txt) được lưu kèm. SHA-256: `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`.

Kiểm tra bảng ký tự bằng fontTools: đủ dải tiếng Việt U+1EA0–U+1EF9, Ă/Đ/Ĩ/Ũ/Ơ/Ư và chữ thường tương ứng; đủ các dấu tổ hợp grave/acute/tilde/hook/dot/circumflex/breve/horn. Trình duyệt tải Inter thành công; sprite có hình học hiển thị ở cả hai trình duyệt.

### Chạy lại kiểm tra

Không thêm bước build vào web. Playwright chỉ là công cụ kiểm thử cục bộ:

```powershell
npm install --prefix .lan/u1-tools --no-save --no-package-lock --no-audit --no-fund playwright@1.65.1
$env:UI_BASE_URL = 'http://localhost:8000'
node tools/check-ui-u1.cjs
.venv/Scripts/ruff.exe check backend
.venv/Scripts/ruff.exe format --check backend
.venv/Scripts/python.exe -m pytest backend/tests/unit -q
```

Cần Chrome và Edge đã cài. Ảnh mới và JSON mặc định ở `.lan/u1-results/` (không đưa vào Git); đặt `UI_SCREENSHOTS` nếu muốn đổi thư mục. Bộ nghiệm thu này chạy với máy chủ dev cục bộ ở cổng 8031, tắt lifespan để không cần kết nối database; không kiểm tra luồng gọi video.

## Ảnh nghiệm thu

| Trình duyệt / kích thước | Sáng | Tối |
|---|---|---|
| Chrome / 1440 | [Ảnh sáng](assets/u1/u1-chrome-desktop-light.png) | [Ảnh tối](assets/u1/u1-chrome-desktop-dark.png) |
| Chrome / 900 | [Ảnh sáng](assets/u1/u1-chrome-tablet-light.png) | [Ảnh tối](assets/u1/u1-chrome-tablet-dark.png) |
| Chrome / 390 | [Ảnh sáng](assets/u1/u1-chrome-phone-light.png) | [Ảnh tối](assets/u1/u1-chrome-phone-dark.png) |
| Edge / 1440 | [Ảnh sáng](assets/u1/u1-msedge-desktop-light.png) | [Ảnh tối](assets/u1/u1-msedge-desktop-dark.png) |
| Edge / 900 | [Ảnh sáng](assets/u1/u1-msedge-tablet-light.png) | [Ảnh tối](assets/u1/u1-msedge-tablet-dark.png) |
| Edge / 390 | [Ảnh sáng](assets/u1/u1-msedge-phone-light.png) | [Ảnh tối](assets/u1/u1-msedge-phone-dark.png) |

## Giới hạn và bước sau

- Chưa có hai ảnh mockup ConnectV gốc trong repo để lấy màu trực tiếp hoặc đối chiếu từng chi tiết. Bộ màu triển khai dựa vào đặc tả mục 3 và điều chỉnh tương phản; đây là điểm cần người dùng duyệt bằng trang mẫu.
- Chưa thử trên Safari/iPhone thật. Viewport 390 px trên Windows không thay thế nghiệm thu thiết bị thật.
- U2–U7 và E1–E7 chưa triển khai trong thay đổi này. Router/store, màn hình người dùng mới, trang admin mới và kết nối dữ liệu thật thuộc các giai đoạn tiếp theo.
- Nhánh này được push để kiểm tra, chưa merge vào `main`.
