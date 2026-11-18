# Idea: Ý tưởng mới cho dự án

> Đây là **nơi ghi mọi ý tưởng mới** của dự án. Ý tưởng ở đây là **đề xuất chưa cam kết**: chưa có thiết kế chi tiết, chưa nằm trong lộ trình.
> Bổ sung cho `docs/` và `docs_v3/` (`extend.md`, `ui.md`). Quy tắc làm việc giữ nguyên: ý tưởng muốn làm thật thì **phải qua phân tích và vào tài liệu trước**, rồi mới code.
> Các mã `I-xx` đã được `extend.md` và `ui.md` tham chiếu, nên **không đổi số khi sắp xếp lại**; ý tưởng mới thì thêm số tiếp theo.

## 1. Cách đọc file này

| Cột | Ý nghĩa |
|---|---|
| **Giá trị** | 1-5: lợi ích cho người dùng, cho báo cáo/học tập, hoặc cho độ an toàn |
| **Công sức** | **S** (vài giờ đến 1 ngày), **M** (vài ngày), **L** (1-2 tuần), **XL** (nhiều tuần hoặc nhiều rủi ro) |
| **Phụ thuộc** | Bước trong `docs/` hoặc `extend.md` cần có trước |
| **Học được** | Kỹ năng đáng giá nhất (ưu tiên định hướng backend và devops của bạn) |

Ràng buộc của dự án (dùng để lọc ý tưởng): **chạy miễn phí** trên máy chính hoặc máy nhỏ (`09-homelab-deployment.md`), **đa thiết bị đa mạng**, **dữ liệu lưu trên máy chính**, ưu tiên **học devops**. Ý tưởng cần tài nguyên lớn hoặc dịch vụ trả phí đều ghi rõ.

## 2. Đề xuất thứ tự (nếu chỉ chọn một ít)

Sắp theo "giá trị / công sức" và mức phù hợp với mục tiêu của bạn:

| Thứ tự | Ý tưởng | Vì sao nên sớm |
|---|---|---|
| 1 | **I-31** Quét bảo mật trong CI (Dependabot, gitleaks, Trivy) | Dễ (S), dạy DevSecOps, chạy miễn phí, bắt lỗi bí mật bị lộ ngay từ đầu |
| 2 | **I-06** Thu thập chất lượng cuộc gọi (QoS) | Cung cấp **số liệu thật** chứng minh mục tiêu độ trễ < 200 ms; biến thẻ "QoS" của admin thành dữ liệu thật |
| 3 | **I-27 + I-07** PWA và thông báo đẩy web | Lấp lỗ hổng lớn nhất của `extend.md`: không nhận được lời mời gọi khi đóng ứng dụng |
| 4 | **I-02** Phòng chờ và khóa phòng | Nâng độ an toàn khi mở ứng dụng ra Internet qua Funnel |
| 5 | **I-35** Quan sát nâng cao (Loki, theo dõi truy vết, SLO) | Học devops sâu, tận dụng Prometheus/Grafana đã có |
| 6 | **I-37** Sao lưu tự động và kiểm tra khôi phục tự động | Dữ liệu nằm trên một máy duy nhất; tăng độ tin cậy |
| 7 | **I-22** Người đang nói nổi bật, ghim video | Cải thiện trải nghiệm nhiều, công sức vừa |
| 8 | **I-21** Chế độ tiết kiệm băng thông | Hợp với mạng di động, dễ đo hiệu quả |
| 9 | **I-12** Quên mật khẩu và xác minh email | Cần cho người dùng thật; phụ thuộc dịch vụ gửi email |
| 10 | **I-01** Lịch họp | Có trong mockup; giá trị cao nhưng công sức vừa-lớn |

Ghi lại **lý do** nếu bạn đổi thứ tự (để dùng cho báo cáo).

## 3. Ý tưởng cho người dùng cuối

### 3.1 Từ mockup (chưa có backend)

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-01** | **Lịch họp:** đặt lịch phòng họp (tên, giờ, người mời), nhắc trước giờ, hiển thị "Cuộc họp hôm nay" như mockup, xuất tệp `.ics` | 5 | M-L | A4, E2 | Thêm bảng `meetings`, tác vụ nhắc giờ; cần múi giờ rõ ràng (lưu UTC, hiển thị theo máy người dùng); nhắc khi đóng ứng dụng cần I-07 |
| **I-03** | **Ghi hình cuộc họp** (và nút "Xem bản ghi") | 4 | XL | A10 (SFU) | Cần SFU hoặc client ghi; tốn CPU/đĩa, **cần xin sự đồng ý của người tham gia và hiển thị rõ đang ghi**; ⚠ kiểm tra quy định về dữ liệu cá nhân |
| **I-04** | **Transcript giọng nói và phụ đề trực tiếp** (nút "Tải Transcript") | 4 | XL | I-03 hoặc luồng âm thanh ở SFU | Nhận dạng giọng nói local rất nặng cho máy yếu; dịch vụ ngoài thì có chi phí và gửi âm thanh ra ngoài; **ở bản đầu dùng "Tải nhật ký chat"** |
| **I-05** | **Tóm tắt cuộc họp bằng AI** từ transcript hoặc chat | 3 | L | I-04 | Chi phí và quyền riêng tư (nội dung họp gửi cho bên thứ ba); có thể giới hạn cho nhật ký chat, bật theo từng phòng |
| **I-06** | **Thu thập chất lượng cuộc gọi (QoS):** client gửi mẫu tóm tắt từ `getStats()` (RTT, mất gói, bitrate, loại kết nối) mỗi 10-30 giây; server tổng hợp → thẻ "QoS" của admin và biểu đồ theo thời gian | 5 | M | A9, A11 | Không thu thông tin nhận dạng cá nhân; lượng dữ liệu nhỏ (gộp phía client); là **nguồn số liệu chính cho báo cáo** |
| **I-10** | **Mã hóa đầu cuối (E2EE)** cho cuộc gọi (nhãn "E2E" của mockup) | 3 | XL | A10 | Với mesh P2P, media đã mã hóa theo từng kết nối (DTLS-SRTP) nhưng **không phải E2EE qua SFU**; E2EE qua SFU cần cơ chế khóa phức tạp. Đừng gắn nhãn "E2E" vào giao diện nếu chưa làm thật |
| **I-17** | **Hồ sơ mở rộng:** chức danh (như "Product Manager" ở mockup), giới thiệu ngắn, **trạng thái tùy chỉnh** ("Đang bận"), chế độ **Không làm phiền** chặn lời mời gọi | 3 | S-M | E1, E3 | Thêm cột/bảng nhỏ; quyền riêng tư: người xem là bạn bè |

### 3.2 Trải nghiệm cuộc gọi

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-02** | **Phòng chờ (waiting room)** và **khóa phòng**: host duyệt người vào; khóa phòng sau khi đủ người | 4 | M | A4 | Thêm trạng thái "chờ duyệt" trong RAM và sự kiện mới (`join_pending`, `admit`, `deny`); hợp với cách deploy công khai |
| **I-18** | Phản ứng nhanh (emoji), giơ tay có hàng đợi, **bình chọn (poll)** trong phòng | 3 | M | A8 | Dữ liệu tạm trong RAM của phòng; poll có thể lưu vào lịch sử |
| **I-19** | **Bảng trắng** hoặc **ghi chú chung** trong phòng | 3 | L | A8 | Đồng bộ trạng thái giữa nhiều người; có thể dùng DataChannel hoặc Socket.io |
| **I-20** | **Nền ảo** và **khử tiếng ồn** phía client | 3 | M-L | A5 | Xử lý trên máy người dùng nên tốn CPU/pin điện thoại; nên có công tắc tắt; ⚠ kiểm tra thư viện phù hợp |
| **I-21** | **Chế độ tiết kiệm băng thông:** chỉ âm thanh, hoặc tự giảm độ phân giải/fps khi mạng yếu | 4 | M | A9, I-06 | Dùng `RTCRtpSender.setParameters` và dữ liệu `getStats`; đo hiệu quả bằng kịch bản mạng xấu ở `08` |
| **I-22** | **Người đang nói nổi bật**, ghim/spotlight, hai chế độ xem (lưới, người nói) | 4 | M | A9 | Dựa vào mức âm thanh từ `getStats` |
| **I-24** | **Vai trò trong phòng:** đồng chủ trì, người trình bày, quyền chia sẻ màn hình theo phòng; **tắt tiếng tất cả** | 3 | M | A4 | Mở rộng quy tắc quyền ở `03-socket-events.md` mục 4 |
| **I-25** | Chia sẻ màn hình **kèm âm thanh**, **hình trong hình (PiP)** | 3 | S-M | A8 | Hỗ trợ khác nhau giữa trình duyệt; ghi vào ma trận ở `08` |
| **I-26** | **Liên kết mời và mã QR**; khách vào bằng liên kết có hạn | 3 | S-M | A4 | Liên kết mang mã phòng (không mang mật khẩu); hết hạn theo cấu hình |

### 3.3 Mạng xã hội và liên lạc

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-07** | **Thông báo đẩy** cho lời mời gọi, tin nhắn, lời mời kết bạn khi đóng ứng dụng (Web Push; FCM/APNs cho app di động) | 5 | M-L | E3, I-27 | Cần khóa VAPID và lưu đăng ký của từng thiết bị; ⚠ trên iPhone thường yêu cầu cài ứng dụng web ra màn hình chính và phiên bản iOS phù hợp, kiểm tra khi làm |
| **I-08** | **Chat nhóm** và **nhóm bạn bè** | 4 | L | E4 | Mở rộng `conversations` (loại `group`, bảng thành viên); thiết kế đã chừa chỗ |
| **I-09** | **Gửi ảnh/tệp** trong tin nhắn | 3 | M-L | E4 | Dùng lại quy trình xử lý ảnh an toàn của avatar; giới hạn dung lượng, quét loại tệp; tốn đĩa trên máy chính |
| **I-11** | **Báo cáo vi phạm và kiểm duyệt:** báo cáo người dùng/tin nhắn, hàng đợi cho admin, chỉ xem **nội dung bị báo cáo** và ghi audit | 4 | M | E4, E7 | Cân bằng quyền riêng tư (admin không đọc tin riêng nói chung) |
| **I-27** | **PWA** (cài ứng dụng web lên máy/điện thoại, mở như ứng dụng) | 4 | S-M | U2 | Thêm manifest và service worker; **nền tảng cho I-07**; chú ý bộ nhớ đệm không làm cũ giao diện sau khi deploy |
| **I-28** | **Giao diện tiếng Anh** và phím tắt (M tắt mic, V tắt camera, ...) | 2 | S-M | U2 | Có sẵn `i18n/vi.js` nên chi phí thấp |

### 3.4 Livestream

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-23** | **Livestream nâng cao:** đếm người xem, bình luận có kiểm duyệt, nâng người xem lên người nói; **HLS dự phòng** cho số người xem lớn | 3 | XL | A10 | HLS cần chuyển mã (ffmpeg) nên rất tốn CPU; chỉ làm nếu SFU đã ổn |

## 4. Ý tưởng về tài khoản và bảo mật

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-12** | **Quên mật khẩu** và **xác minh email** | 4 | M | A2 | Cần dịch vụ gửi email (SMTP); ⚠ dịch vụ miễn phí có hạn mức, kiểm tra trước; token một lần, hết hạn ngắn, lưu băm |
| **I-13** | **Đăng nhập Google/GitHub (OAuth)** | 3 | M | A2 | Thêm bảng liên kết danh tính; cẩn thận khi hợp nhất với tài khoản email cùng địa chỉ |
| **I-14** | **Xác thực hai bước (TOTP)** | 4 | M | A2 | Mã dự phòng, giới hạn thử, thu hồi phiên khi bật/tắt |
| **I-15** | **Xóa tài khoản** và **xuất dữ liệu cá nhân** | 4 | M | E1-E6 | Xử lý hết mọi bảng liên quan (xem quy tắc `ON DELETE` ở `01-database.md` mục 4 và `extend.md`); cần xác nhận bằng mật khẩu |
| **I-16** | **Đổi email an toàn** (xác minh email mới, thông báo email cũ) | 3 | M | I-12 | Email là khóa tìm bạn và đăng nhập nên phải có xác minh |
| **I-41** | **Vai trò admin phân cấp:** Super Admin, Kiểm duyệt viên, Hỗ trợ (mockup có nhãn "Super Admin") | 3 | M | A3 | Mở rộng cột `role` bằng `CHECK`; quyền theo hành động; đừng làm phức tạp nếu chỉ có một admin |
| **I-42** | **Cảnh báo bất thường:** đăng nhập từ thiết bị/vị trí lạ, nhiều lần đăng nhập sai, spam lời mời | 3 | M | A3, A11 | Dùng log và metric đã có; gửi cảnh báo qua Telegram/Discord |
| **I-44** | **Danh sách chặn** theo email, tên miền, địa chỉ IP | 2 | S-M | A3 | Lưu ý IP thật có thể không tới được app khi đứng sau Funnel (`09` mục 5) |

## 5. Ý tưởng cho quản trị và phân tích

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Ghi chú và rủi ro |
|---|---|---|---|---|---|
| **I-43** | **Báo cáo định kỳ** (CSV/PDF), gửi theo lịch | 2 | M | A6 | Cần email hoặc nơi lưu; có thể chỉ tạo tệp và tải về |
| **I-45** | **Bản đồ nhiệt giờ cao điểm** và thống kê sử dụng theo thiết bị/trình duyệt | 3 | M | I-06 | Chỉ dùng số liệu tổng hợp ẩn danh |
| **I-46** | **Cờ tính năng (feature flags)** qua trang cấu hình (bật thử cho một nhóm người dùng) | 3 | S-M | A3 | Mở rộng `SettingsSchema`; dạy phát hành dần dần |

## 6. Ý tưởng DevOps và hạ tầng (hợp mục tiêu học tập)

| ID | Ý tưởng | Giá trị | Công sức | Phụ thuộc | Học được |
|---|---|---|---|---|---|
| **I-30** | **Hạ tầng dưới dạng mã (IaC):** Terraform hoặc Ansible dựng máy chủ, firewall, cài Docker tự động | 4 | M | B1 (cloud) | IaC, tính lặp lại; chỉ có ý nghĩa khi dùng cloud, với máy chính thì có thể dùng Ansible để cấu hình máy |
| **I-31** | **Quét bảo mật trong CI:** Dependabot (cập nhật thư viện), gitleaks (bí mật), Trivy (lỗ hổng image), tạo SBOM | 5 | S | A1 | DevSecOps, an toàn chuỗi cung ứng |
| **I-32** | **Triển khai không gián đoạn:** blue-green hoặc canary với Caddy | 3 | M-L | H6/B4 | Chiến lược phát hành; lưu ý trạng thái phòng nằm trong RAM nên đổi phiên bản vẫn làm rớt cuộc gọi trừ khi có Redis (I-39) |
| **I-33** | **k3s/Kubernetes** (học tập) chạy cùng stack | 2 | XL | B4 | Điều phối container; vượt quá nhu cầu của dự án, chỉ làm để học |
| **I-34** | **Kiểm thử tải và hỗn loạn:** k6/Locust cho HTTP, bot aiortc cho WebRTC (đã có ở B6), kịch bản tắt DB/app/mạng giữa cuộc gọi | 4 | M | B6 | Chịu lỗi, đo giới hạn, viết runbook |
| **I-35** | **Quan sát nâng cao:** Loki cho log tập trung, theo dõi truy vết (OpenTelemetry), **SLO và cảnh báo theo tốc độ tiêu hao ngân sách lỗi** | 4 | M-L | A11, B5 | Observability chuyên sâu, SRE cơ bản |
| **I-36** | **Trang trạng thái (status page)** và giám sát từ bên ngoài | 3 | S-M | B5 | Giao tiếp sự cố |
| **I-37** | **Sao lưu nâng cao:** sao lưu mã hóa (restic hoặc tương tự) ra nơi khác, **kiểm tra khôi phục tự động hằng tuần** | 5 | M | H7/B7 | Sao lưu, RPO/RTO; kiểm tra khôi phục tự động là thứ ít người làm |
| **I-39** | **Redis và nhiều instance** (đã nêu ở `06-decisions.md`) | 3 | L | A4 | Mở rộng ngang; chuyển trạng thái phòng và rate limit sang Redis |
| **I-40** | **SFU nâng cao:** so sánh aiortc với mediasoup/LiveKit, simulcast, đo số người xem tối đa | 4 | XL | A10 | So sánh công nghệ có số liệu, rất tốt cho báo cáo |
| **I-47** | **Pre-commit hooks** (ruff, kiểm tra bí mật) và quy tắc bảo vệ nhánh `main` | 3 | S | A1 | Chất lượng ngay từ máy cục bộ |

## 7. Ý tưởng cần cân nhắc kỹ hoặc nên tránh

| Ý tưởng | Lý do thận trọng |
|---|---|
| E2EE qua SFU (I-10) | Phức tạp về quản lý khóa; làm nửa vời còn nguy hiểm hơn không làm; hiển thị nhãn "E2E" khi chưa đúng là gây hiểu lầm cho người dùng |
| Ghi hình và transcript (I-03, I-04) | Nặng tài nguyên, có vấn đề **đồng ý và quyền riêng tư**; cần thiết kế thông báo, quyền truy cập, thời hạn lưu |
| AI tóm tắt (I-05) | Chi phí và gửi nội dung họp cho bên thứ ba; nếu làm, **mặc định tắt** và chỉ chạy khi mọi người đồng ý |
| Kubernetes (I-33) | Đòi hỏi tài nguyên và thời gian lớn so với quy mô dự án |
| Tự chạy coturn công khai tại nhà | Lộ địa chỉ IP nhà và phụ thuộc vào mạng của nhà cung cấp (xem `09` mục 6) |
| Nhiều tính năng "cho đẹp" trước khi test đa thiết bị | Rủi ro lớn nhất của dự án là **gọi khác mạng không ổn**, ưu tiên test ở `08` trước |

## 8. Ý tưởng theo mục tiêu của bạn

| Mục tiêu | Ý tưởng nên xem trước |
|---|---|
| **Học DevOps ở mức sâu** | I-31, I-35, I-37, I-34, I-32, I-47, I-30 |
| **Báo cáo có số liệu thuyết phục** | I-06, I-34, I-40, I-21 (đo hiệu quả), I-35 |
| **Trải nghiệm người dùng thật** | I-27 + I-07, I-02, I-22, I-01 |
| **An toàn khi mở ứng dụng ra Internet** | I-02, I-14, I-42, I-44, I-31 |
| **Hoàn thiện hệ thống tài khoản** | I-12, I-16, I-15, I-14 |

## 9. Cách đưa một ý tưởng vào kế hoạch

```
Ý tưởng (file này)  →  Phân tích ngắn (mục tiêu, dữ liệu, API, sự kiện, rủi ro)
        →  Thêm vào tài liệu (docs_v3/…)  →  Gán bước và migration
        →  Cập nhật AGENT_PROMPT.md  →  Code
```

Điều kiện để chuyển một ý tưởng thành bước thật:
1. Đã **chọn ý tưởng** (ghi lý do vào `docs/06-decisions.md`).
2. Đã **ước lượng công sức** và kiểm tra phù hợp với máy chạy (RAM, đĩa, băng thông).
3. Đã **thiết kế dữ liệu và quyền riêng tư** (ai thấy gì, lưu bao lâu).
4. Có **cách kiểm thử** (kể cả thiết bị và mạng cần cho bước đó).

## 10. Mẫu để thêm ý tưởng mới

Sao chép mẫu này vào mục phù hợp ở trên, đánh số `I-` tiếp theo (số lớn nhất hiện tại là **I-47**):

```
| I-xx | **Tên ý tưởng:** mô tả một hai câu | 1-5 | S/M/L/XL | bước cần có trước | rủi ro, lưu ý, quyền riêng tư |
```

Nếu ý tưởng có ba điều trở lên cần giải thích (luồng, dữ liệu, rủi ro), viết thêm một mục riêng ở cuối file này với tiêu đề `## Ý tưởng chi tiết: I-xx`.

## 11. Câu hỏi để chọn hướng

| # | Câu hỏi | Ảnh hưởng |
|---|---|---|
| Q23 | **[CẦN CHỐT]** Bạn muốn ưu tiên **học devops**, **số liệu cho báo cáo**, hay **trải nghiệm người dùng**? | Quyết định thứ tự ở mục 2 và 8 |
| Q24 | Có cần người dùng thật (bạn bè dùng thử) hay chỉ demo? | Nếu có người dùng thật: ưu tiên I-12, I-27 + I-07, I-02, I-14 |
| Q25 | Thời gian còn lại cho phần ngoài `extend.md` và `ui.md`? | Quyết định chỉ chọn mục S/M hay cả L |

## 12. Việc cần cập nhật ở các tài liệu khác

| File | Cập nhật |
|---|---|
| `docs/README.md` | Nhắc `docs_v3/idea.md` ở mục phạm vi mở rộng |
| `docs/06-decisions.md` | Khi chọn một ý tưởng thì thêm quyết định (D-xx) và lý do |
| `docs_v3/ui.md` | Mục 8 đã tham chiếu I-01, I-03, I-04, I-06, I-10, I-17; giữ số hiệu khớp |
