# Thử nghiệm aiortc cho A10

Thử nghiệm dùng Python 3.12, aiortc 1.16.0, aioice 0.13.0 và PyAV 19.0.2. Một publisher gửi video VP8 640×360 ở 15 FPS. Tiến trình aiortc riêng nhận video, chuyển khung qua `MediaRelay` với `buffered=False` và mã hóa lại cho từng viewer. Publisher và các viewer aiortc chạy trên cùng máy với tiến trình chuyển tiếp.

## Cách đo

Video tổng hợp mã hóa thời điểm tạo khung vào các ô sáng tối. Viewer đọc lại thời điểm đó sau khi giải mã để tính độ trễ một chiều của cả hai chặng. Mỗi lượt chờ tất cả viewer nhận khung, chờ thêm một giây rồi đo. CPU là tỷ lệ sử dụng quy theo một lõi logic. RAM là RSS lớn nhất trong các mẫu mỗi giây của riêng tiến trình chuyển tiếp. FPS thấp nhất được lấy trên toàn bộ viewer trong từng lượt.

Chạy từ thư mục gốc dự án trong PowerShell.

```powershell
$spikeEnv = Join-Path $env:TEMP 'videocall-a10-spike'
python -m venv $spikeEnv
$spikePython = Join-Path $spikeEnv 'Scripts\python.exe'
& $spikePython -m pip install --only-binary=:all: -r loadtest/requirements-aiortc-spike.txt
& $spikePython loadtest/aiortc_spike.py --viewers 1 2 4 8 --seconds 12
```

## Kết quả trên Windows

Máy dev có 12 CPU logic. Mỗi lượt đo khoảng 12 giây. Tất cả viewer nhận được video.

| Viewer | FPS thấp nhất | Độ trễ p50 | Độ trễ p95 | CPU quy theo 1 lõi | RSS đỉnh trong mẫu |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 15,0 | 141 ms | 157 ms | 4,7% | 76,1 MiB |
| 2 | 15,0 | 141 ms | 157 ms | 9,5% | 90,2 MiB |
| 4 | 15,1 | 141 ms | 157 ms | 20,1% | 116,3 MiB |
| 8 | 15,0 | 141 ms | 172 ms | 54,8% | 169,9 MiB |

Kết quả mô tả video tổng hợp có độ phức tạp thấp trên cùng máy. Các biến cần đo để chốt sức chứa vận hành gồm video camera thật, audio, nhiều nguồn phát, TURN, hai mạng khác nhau và thời gian chạy dài hơn.

## Dải cổng UDP

`RTCConfiguration` của aiortc chỉ có các lựa chọn về ICE server, chính sách ICE, bundle và data channel. aioice 0.13.0 gọi `bind` qua `create_datagram_endpoint` với cổng 0, nên hệ điều hành cấp cổng UDP động. Dải IPv4 UDP của máy Windows thử nghiệm là 49152–65535. SDP của phía chuyển tiếp trong bốn lượt trên chứa các cổng từ 59361 đến 65352. [API aiortc](https://aiortc.readthedocs.io/en/latest/api.html#aiortc.RTCConfiguration) · [Mã aioice](https://github.com/aiortc/aioice/blob/0.13.0/src/aioice/ice.py)

Lệnh sau kiểm tra dải cổng trong namespace mạng bridge của một container Linux tạm. `ip_local_port_range` điều khiển cấp cổng động trong namespace đó. [Docker](https://docs.docker.com/reference/cli/docker/container/run/#sysctl) · [Linux kernel](https://www.kernel.org/doc/html/latest/networking/ip-sysctl.html#ip-variables)

```powershell
$fixtureDir = (Resolve-Path loadtest).Path
docker run --rm --memory=768m --sysctl "net.ipv4.ip_local_port_range=40000 40127" `
  --mount "type=bind,source=$fixtureDir,target=/experiment,readonly" python:3.12-slim `
  sh -ec 'cat /proc/sys/net/ipv4/ip_local_port_range; pip install --no-cache-dir --only-binary=:all: -r /experiment/requirements-aiortc-spike.txt; python -B /experiment/aiortc_spike.py --viewers 1 4 --seconds 8'
```

Cả hai lượt đều nhận video và chỉ có cổng UDP nằm trong dải cấu hình:

| Viewer | FPS thấp nhất | Độ trễ p95 | CPU quy theo 1 lõi | RSS đỉnh trong mẫu | Cổng UDP quan sát |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 15,1 | 144,3 ms | 6,9% | 84,0 MiB | 40046, 40051 |
| 4 | 15,0 | 147,5 ms | 21,9% | 141,4 MiB | 40003, 40019, 40020, 40039, 40069 |

Mẫu Docker đo tám giây. Các peer và tiến trình chuyển tiếp ở cùng namespace bridge. Phép thử kết nối từ bên ngoài container sẽ cần xác minh cả cổng được publish lẫn địa chỉ mà client nhận trong ICE.

## Đề xuất triển khai livestream sau khi duyệt

1. Mở đầu với **một nguồn phát 360p/15 FPS và tối đa bốn viewer mỗi phòng livestream**. Dùng kết quả ở 8 viewer làm mốc cho phép thử nâng sức chứa khi có audio, camera thật và mạng khác nhau.
2. Dùng một `RTCPeerConnection` giữa mỗi client và SFU cho livestream. App tiếp tục xác thực, kiểm tra thành viên phòng và xử lý quyền host qua Socket.IO. Host quản lý một suất phát bằng `promote_speaker` và `demote_speaker`. Viewer chỉ nhận media khi chưa được cấp quyền phát.
3. Chạy tiến trình chuyển tiếp trong container Linux riêng để đo và giới hạn tài nguyên. Xác minh mapping cổng UDP và địa chỉ ICE từ trình duyệt bên ngoài container trước khi mở quyền truy cập qua LAN. Đo riêng đường TURN trong phép thử tiếp theo.
4. Chỉ nâng giới hạn khi viewer giữ được FPS và độ trễ mục tiêu trên cấu hình triển khai. Đo mức CPU/RSS của SFU riêng với các chỉ số app và TURN.
