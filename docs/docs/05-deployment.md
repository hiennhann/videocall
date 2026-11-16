# 05. Triển khai và DevOps

> Chạy Docker từ bước A1 để giai đoạn B chỉ còn là "mang lên server".
> Tài liệu này gồm: container, mạng và cổng, coturn, Caddy, CI/CD, giám sát, backup, load test.

## 1. Danh sách container

| Service | Image | Vai trò | Dev | Prod |
|---|---|---|---|---|
| `db` | `postgres:16` | Cơ sở dữ liệu | Có | Có |
| `migrate` | Image của app | Chạy `alembic upgrade head` rồi **thoát** | Có | Có |
| `app` | Image của app | FastAPI + Socket.io, **1 worker** | Có | Có |
| `coturn` | `coturn/coturn` | STUN/TURN | Có (xem 4.4) | Có |
| `caddy` | `caddy:2` | HTTPS, reverse proxy, WebSocket | Không | Có |
| `prometheus` | `prom/prometheus` | Thu thập metric | Tùy chọn | Có |
| `grafana` | `grafana/grafana` | Dashboard | Tùy chọn | Có |
| `node-exporter` | `prom/node-exporter` | Metric máy chủ (CPU, RAM, đĩa, mạng) | Không | Có |
| `redis` | `redis:7` | Trạng thái phòng, rate limit | Chưa | Chưa (khi cần) |

Thứ tự khởi động: `db` (healthy) → `migrate` (thành công) → `app` (healthy) → `caddy`.

```yaml
# phác thảo docker-compose.yml
services:
  db:
    image: postgres:16
    environment: { POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB }
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"], interval: 5s, retries: 10 }

  migrate:
    build: ./backend
    command: alembic upgrade head
    depends_on: { db: { condition: service_healthy } }
    restart: "no"

  app:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
    depends_on:
      db: { condition: service_healthy }
      migrate: { condition: service_completed_successfully }
    healthcheck: { test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/ready')"], interval: 10s }
```

**Không để app tự migrate khi khởi động**, vì nhiều instance sẽ tranh nhau. Dùng service `migrate` riêng.

**`--workers 1` là bắt buộc** ở v1 vì trạng thái phòng nằm trong RAM của process (`03-socket-events.md` mục 3).

## 2. Sơ đồ mạng

```
                       Internet
                          │
   ┌──────────────────────┼───────────────────────────┐
   │ VPS (IP công khai)   │                           │
   │                      │                           │
   │  80,443/tcp ─────▶ [caddy] ──http/ws──▶ [app:8000] ──▶ [db:5432]
   │                                            │
   │  3478/udp+tcp ───▶ [coturn] (network_mode: host)      │ /metrics
   │  5349/tcp (TURNS, tùy chọn)                           ▼
   │  49152-49252/udp ▶ [coturn] relay           [prometheus:9090] ◀─ [node-exporter]
   │                                                    ▲
   │  (chỉ nội bộ / qua tunnel) ─────────────────▶ [grafana:3000]
   └──────────────────────────────────────────────────────┘
```

Hai mạng Docker:
- `frontend`: `caddy` ↔ `app`, `grafana`
- `backend`: `app` ↔ `db`, `prometheus`

`db` chỉ nằm trong `backend`, **không publish cổng** ra host.

## 3. Cổng cần mở (firewall)

| Cổng | Giao thức | Dịch vụ | Mở ra Internet? |
|---|---|---|---|
| 22 | TCP | SSH | Có (khuyến nghị đổi cổng hoặc giới hạn IP, chỉ dùng key) |
| 80 | TCP | Caddy (xác thực Let's Encrypt, chuyển hướng HTTPS) | Có |
| 443 | TCP (+UDP cho HTTP/3) | Caddy | Có |
| 3478 | UDP + TCP | coturn STUN/TURN | Có |
| 5349 | TCP | coturn TURNS (TLS), tùy chọn | Có |
| 49152-49252 | UDP | Dải relay của coturn | Có |
| 8000, 5432, 9090, 3000 | TCP | app, db, Prometheus, Grafana | **Không** (nội bộ) |
| (A10) dải UDP của SFU | UDP | aiortc | Có, khi có SFU |

Công cụ: `ufw` trên VPS **và** firewall của nhà cung cấp VPS (đừng quên lớp này, đây là lỗi hay gặp: mở `ufw` nhưng cổng UDP vẫn bị chặn ở panel của nhà cung cấp).

Dải relay `49152-49252` là 101 cổng ≈ tối đa ~100 relay allocation cùng lúc. Đủ cho đồ án; tăng nếu cần.

## 4. coturn

### 4.1 Cấu hình `deploy/coturn/turnserver.conf`

```conf
listening-port=3478
tls-listening-port=5349
min-port=49152
max-port=49252

realm=turn.example.com
server-name=turn.example.com

# Credential tạm thời theo HMAC (khớp turn_service.py)
use-auth-secret
static-auth-secret=__TURN_SECRET__      # tiêm lúc chạy, KHÔNG commit giá trị thật

fingerprint
no-multicast-peers
no-cli
no-tlsv1
no-tlsv1_1

# Chống dùng TURN để chọc vào mạng nội bộ (SSRF)
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=100.64.0.0-100.127.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255

# Giới hạn để bảo vệ băng thông VPS
user-quota=12            # số allocation đồng thời / credential
total-quota=100          # tổng allocation
max-bps=2000000          # tốc độ tối đa / allocation (bit/s), ~2 Mbps
stale-nonce=600

# Khi VPS nằm sau NAT (AWS, GCP, Oracle...), cần khai báo:
# external-ip=<PUBLIC_IP>/<PRIVATE_IP>

# TLS (chỉ khi bật TURNS), dùng chứng chỉ của Caddy mount vào, read-only
# cert=/certs/turn.example.com.crt
# pkey=/certs/turn.example.com.key

prometheus               # metric ở cổng 9641 (kiểm tra theo phiên bản coturn đang dùng)
log-file=stdout
simple-log
```

Các tùy chọn trên là cấu hình phổ biến của coturn; **kiểm tra lại tên và hiệu lực theo phiên bản bạn cài** (`turnserver --help`) khi làm bước B3.

### 4.2 Vì sao `network_mode: host`

Map một dải UDP lớn qua Docker bridge tốn tài nguyên (mỗi cổng một tiến trình proxy) và khiến coturn thấy sai địa chỉ nguồn. Trên Linux VPS dùng `network_mode: host` cho coturn là cách đơn giản và ổn định nhất. Đây chính là cái bẫy sẽ gặp ở bước A7.

### 4.3 DNS và Cloudflare

- Dùng hai tên: `app.example.com` (Caddy) và `turn.example.com` (coturn), cùng trỏ về IP VPS.
- Nếu dùng Cloudflare: **`turn.example.com` phải để "DNS only" (đám mây xám)**. Proxy của Cloudflare không chuyển được UDP nên TURN sẽ hỏng. Với `app.example.com` bật proxy hay không đều được, nhưng khi có SFU (UDP trực tiếp) nên để DNS only.

### 4.4 Chạy coturn ở môi trường dev

| Hệ điều hành | Cách làm |
|---|---|
| Linux | `network_mode: host`, giống production |
| Windows / macOS (Docker Desktop) | Compose A7 dùng mạng bridge, ánh xạ `3478/udp`, `3478/tcp` và `49152–49162/udp`. Compose truyền `TURN_HOST` cho `--external-ip` của coturn |

Mặc định `TURN_HOST=127.0.0.1` giới hạn các cổng trên máy dev để gọi trực tiếp. Khi thử ép relay trong Chrome, đặt `TURN_HOST` thành địa chỉ IPv4 LAN của máy chạy Docker Desktop và dùng `TURN_SECRET` ngẫu nhiên, rồi chạy lại `docker compose up --build --wait`. Coturn dùng cặp `--external-ip=<IP LAN>/<IP container>` để chuyển tiếp giữa các allocation trên cùng máy chủ. Trong bản dev, cổng HTTP của ứng dụng vẫn ở localhost.

Compose dùng image `coturn/coturn:4.19.0-r0`. Health check dùng `turnutils_stunclient` để kiểm tra listener. Kiểm thử trên hai mạng thật cần một TURN server mà cả hai thiết bị đều truy cập được.

### 4.5 Kiểm thử TURN

- Công cụ web "Trickle ICE" (nhập URL + username/credential từ `/turn-credentials`), kỳ vọng thấy candidate loại `relay`.
- Chrome: `chrome://webrtc-internals`, xem cặp ICE được chọn.
- Ép dùng relay để kiểm tra: `new RTCPeerConnection({ iceServers, iceTransportPolicy: "relay" })`.

## 5. Caddy (reverse proxy + HTTPS)

```caddy
# deploy/caddy/Caddyfile (phác thảo)
app.example.com {
    encode zstd gzip

    # /metrics không ra Internet
    @metrics path /metrics
    respond @metrics 404

    # Khóa admin bằng IP allowlist (lớp bảo vệ thứ hai ngoài đăng nhập)
    @admin path /admin /admin/* /api/v1/admin/*
    handle @admin {
        @denied not remote_ip {$ADMIN_ALLOWED_IPS}
        respond @denied 403
        reverse_proxy app:8000
    }

    # Mọi thứ còn lại, gồm cả WebSocket (Caddy tự xử lý upgrade)
    reverse_proxy app:8000 {
        header_up X-Real-IP {remote_host}
    }

    header {
        Strict-Transport-Security "max-age=31536000"
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
        Permissions-Policy "camera=(self), microphone=(self), display-capture=(self)"
    }
}
```

Điểm cần nhớ:
- **HTTPS là bắt buộc** thì trình duyệt mới cho truy cập camera/mic (trừ `localhost`). Caddy tự xin và gia hạn chứng chỉ Let's Encrypt; cần mở cổng 80 và 443 và domain đã trỏ về VPS trước.
- **Không dùng HTTP Basic Auth để khóa `/admin`**: Basic Auth dùng chính header `Authorization`, xung đột với Bearer token. Dùng IP allowlist hoặc truy cập qua VPN (WireGuard/Tailscale).
- Header `Content-Security-Policy` chặt cho trang admin sẽ thêm ở bước A6, khi biết các nguồn script (HTMX).
- Từ A5, FastAPI phục vụ client tại `/`, `/lobby` và `/room`. Docker image kèm thư mục `client/` và Socket.IO client 4.8.4.

## 6. Quản lý bí mật và môi trường

| Nơi | Cách |
|---|---|
| Local | `.env` (trong `.gitignore`), mẫu ở `.env.example` |
| GitHub Actions | GitHub Secrets / Environments: `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `GHCR_TOKEN`... |
| VPS | `/opt/videocall/.env`, quyền `600`, chủ sở hữu là user deploy |
| Image Docker | **Không** nhúng `.env` hay secret vào image |

Phát hiện lộ secret: bật GitHub secret scanning; thêm `gitleaks` vào CI.

## 7. CI/CD (GitHub Actions)

### 7.1 `ci.yml`: chạy trên mỗi push và pull request

```
checkout
  → setup Python + cache pip
  → ruff check + ruff format --check
  → (tùy chọn) mypy
  → service container: postgres:16
  → alembic upgrade head
  → alembic check            # bắt lỗi "sửa model nhưng quên tạo migration"
  → alembic downgrade base && alembic upgrade head   # kiểm tra downgrade chạy được
  → pytest --cov
  → docker build (không push)
```

### 7.2 `deploy.yml`: chạy khi merge vào `main` (sau khi CI xanh)

```
1. Build image, gắn tag = git SHA (và `latest`)
2. Push lên GHCR: ghcr.io/<user>/videocall-app:<sha>
3. SSH vào VPS, chạy deploy.sh <sha>:
   a. pg_dump backup (nếu có migration mới)
   b. ghi lại tag đang chạy để rollback
   c. docker compose pull
   d. docker compose run --rm migrate
   e. docker compose up -d app
   f. chờ /ready trả 200 (tối đa ~60 giây)
   g. thất bại → quay lại tag cũ, báo lỗi (job đỏ)
4. Smoke test: gọi /health, /ready, /api/v1/config/public từ bên ngoài
```

Dùng **image gắn tag SHA**, không dùng `latest` để triển khai, để biết chính xác đang chạy bản nào và rollback được.

### 7.3 Rollback

- **Code:** chạy lại `deploy.sh <sha-cũ>`.
- **Database:** `alembic downgrade` chỉ dùng khi chắc chắn. An toàn hơn là viết migration **tương thích ngược** theo hai bước ("mở rộng rồi thu hẹp"): bản N thêm cột mới và vẫn chạy được với schema cũ/mới; chỉ bản N+1 mới bỏ cột cũ. Nhờ vậy rollback code không cần rollback DB.
- Thảm họa: khôi phục từ `pg_dump` (mục 8).

## 8. Backup

| Hạng mục | Cách |
|---|---|
| Tự động hằng ngày | cron trên VPS: `pg_dump -Fc` → `/opt/videocall/backups/` |
| Trước mỗi deploy có migration | `deploy.sh` tự chạy |
| Lưu giữ | 7 bản hằng ngày; (nâng cao) đẩy một bản ra nơi khác, ví dụ object storage |
| **Thử khôi phục** | Mỗi tháng restore vào một DB tạm để chắc rằng bản backup dùng được. Backup chưa từng thử restore thì chưa phải backup |
| Không cần backup | Trạng thái phòng (RAM), TURN |

## 9. Giám sát (observability)

### 9.1 Log
- App ghi **JSON ra stdout** (`structlog`), mỗi dòng có `request_id`, `user_id` (nếu có), `event`, mức log.
- Không ghi mật khẩu, token, SDP đầy đủ.
- Docker: `logging: { driver: json-file, options: { max-size: "10m", max-file: "5" } }` để log không ăn hết đĩa.
- (Sau này) Loki + Grafana nếu muốn tìm log tập trung.

### 9.2 Metric (Prometheus)

| Nguồn | Metric chính |
|---|---|
| app `/metrics` | Request rate/latency/5xx, `socket_connections`, `rooms_active`, `socket_errors_total{code}`, join latency (`03-socket-events.md` mục 10) |
| coturn | Số allocation, băng thông gửi/nhận |
| node-exporter | CPU, RAM, đĩa, băng thông mạng của VPS |
| postgres (tùy chọn) | `postgres-exporter` |

### 9.3 Dashboard Grafana (xuất ra JSON, commit vào `deploy/grafana/`)
1. **Tổng quan:** người online, phòng đang mở, request/giây, tỷ lệ lỗi
2. **Realtime:** kết nối socket, join/giây, lỗi theo mã
3. **Hạ tầng:** CPU, RAM, đĩa, băng thông, băng thông TURN

### 9.4 Cảnh báo (Alertmanager hoặc Grafana alerting → Telegram/Discord)
- App down (`up == 0` > 1 phút)
- Tỷ lệ 5xx > 5% trong 5 phút
- Đĩa > 85%
- Băng thông TURN bất thường (dấu hiệu bị lạm dụng)
- Chứng chỉ sắp hết hạn < 14 ngày (Caddy tự gia hạn; cảnh báo để biết khi nó thất bại)

### 9.5 Đo chất lượng từ phía client
`stats.js` đọc `RTCPeerConnection.getStats()` mỗi giây: RTT (`currentRoundTripTime`), jitter, packet loss, bitrate, fps. Hiển thị ở overlay và (tùy chọn) gửi mẫu về server để vẽ biểu đồ ở báo cáo. **Đây là nguồn số liệu để chứng minh mục tiêu < 200 ms.**

## 10. Tăng cứng VPS (checklist)

- [ ] SSH chỉ dùng key, tắt đăng nhập bằng mật khẩu và đăng nhập root
- [ ] `ufw` chỉ mở các cổng ở mục 3; firewall của nhà cung cấp cấu hình khớp
- [ ] `fail2ban` cho SSH
- [ ] Bật `unattended-upgrades`
- [ ] User riêng để deploy, không chạy thủ công bằng root
- [ ] Container app chạy bằng **user không phải root** (`USER app` trong Dockerfile)
- [ ] `restart: unless-stopped`, giới hạn tài nguyên (`mem_limit`, `cpus`) cho từng service
- [ ] Phiên bản image được ghim (không dùng `latest` cho Postgres, coturn...)
- [ ] `.env` quyền `600`

## 11. Load test (B6)

Mục tiêu: biết giới hạn thật của hệ thống và có số liệu cho báo cáo.

- Thư mục `loadtest/`: bot dùng **aiortc** tạo N `RTCPeerConnection`, phát video giả (`MediaPlayer` hoặc generator), nối vào phòng qua Socket.io như một client thật.
- Kịch bản:

| Kịch bản | Biến thay đổi | Đo |
|---|---|---|
| Signaling | Số socket đồng thời (100 → 1000), join/giây | CPU/RAM app, join latency, lỗi |
| Mesh | 2 → 4 người/phòng, nhiều phòng | Băng thông, CPU máy bot |
| TURN | Ép `iceTransportPolicy: relay`, N luồng | Băng thông relay, CPU coturn, packet loss |
| SFU (A10) | 1 → N subscriber cho 1 publisher | CPU SFU, độ trễ, số subscriber tối đa |

- Chạy bot ở **máy khác** với VPS (nếu không, bot ăn CPU của chính thứ đang đo).
- Xuất kết quả (CSV + ảnh chụp Grafana) vào báo cáo B7.

## 12. Môi trường dev và prod

| | `docker-compose.yml` (dev) | `docker-compose.prod.yml` (ghi đè) |
|---|---|---|
| App | `build:`, mount mã nguồn, `--reload` | `image: ghcr.io/...:${TAG}`, không mount, không `--reload` |
| DB | Có thể publish `5432` ra `localhost` để debug | **Không** publish |
| Caddy, Prometheus, Grafana | Không (hoặc tùy chọn) | Có |
| Restart / giới hạn tài nguyên | Không | Có |
| Log | Dễ đọc (console) | JSON |

Chạy prod: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.

## 13. Thứ tự thực hiện giai đoạn B

| Bước | Việc | Xong khi |
|---|---|---|
| B1 | Thuê VPS, domain, DNS (`app`, `turn`), firewall (cả 2 lớp), SSH key, tăng cứng cơ bản | SSH được, `ufw` đúng, domain trỏ đúng |
| B2 | Caddy + HTTPS, WebSocket qua proxy, khóa `/admin`, ẩn `/metrics` | Vào `https://app...` có ổ khóa, camera/mic được cấp quyền, socket kết nối ổn |
| B3 | coturn production: secret, giới hạn, chặn dải IP nội bộ | Trickle ICE thấy `relay`; gọi 4G ↔ Wi-Fi thành công |
| B4 | CI/CD: test → build → push → deploy → rollback | Merge vào `main` tự triển khai; thử rollback thành công |
| B5 | Prometheus + Grafana + cảnh báo | 3 dashboard hoạt động, cảnh báo thử gửi được |
| B6 | Load test | Có bảng số liệu giới hạn |
| B7 | Báo cáo | Sơ đồ kiến trúc, số liệu đo, bài học, demo |

## 14. Việc cần kiểm chứng khi làm

- Cấu hình coturn: tên tùy chọn và cổng metric theo đúng phiên bản (B3).
- **SFU bằng aiortc:** cần kiểm tra xem có giới hạn được dải cổng UDP hay không. Nếu không, service SFU phải dùng `network_mode: host` hoặc mở dải rộng. Quyết định ở A10.
- Chia sẻ chứng chỉ Caddy cho coturn (nếu bật TURNS): cách mount và tự reload khi gia hạn.
