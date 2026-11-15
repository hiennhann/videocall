# 03. Socket.io: signaling và sự kiện realtime

> Đây là phần cốt lõi của dự án. Server **chỉ trung chuyển tín hiệu**; media đi P2P, qua TURN, hoặc (giai đoạn A10) qua SFU.
> Thư viện: `python-socketio` (`AsyncServer`, `async_mode="asgi"`), mount tại `/socket.io`.

## 1. Kết nối và xác thực

### 1.1 Client kết nối

```js
const socket = io(BASE_URL, {
  auth: { token: accessToken },          // KHÔNG đưa token vào URL/query
  transports: ["websocket"],
  reconnection: true,
});
```

Không dùng query string vì URL bị ghi vào log của proxy.

### 1.2 Server xử lý `connect(sid, environ, auth)`

1. Không có `auth.token` hoặc JWT sai/hết hạn → từ chối.
2. Với user thật: đọc DB, `is_active = false` → từ chối. Nếu `must_change_password` → từ chối. Phiên `family_id` trong JWT phải còn refresh token hợp lệ để tránh kết nối lại sau khi thu hồi phiên.
3. Với khách: kiểm tra `allow_guest = true`.
4. Lưu phiên: `sessions[sid] = { user_id, display_name, role, is_guest, ip, connected_at }`.
5. Thêm `sid` vào `users_online[user_id]` (một user có thể mở nhiều tab).

Từ chối bằng `ConnectionRefusedError(message, {"code": code, "message": message})`. Client nhận ở sự kiện `connect_error` với `err.data.code`:

| code | Ý nghĩa | Client nên |
|---|---|---|
| `UNAUTHENTICATED` / `TOKEN_EXPIRED` | Thiếu/hết hạn token | Refresh token rồi kết nối lại |
| `ACCOUNT_DISABLED` | Bị khóa | Về trang đăng nhập, báo lỗi |
| `GUEST_DISABLED` | Khách bị tắt | Báo lỗi |
| `PASSWORD_CHANGE_REQUIRED` | Phải đổi mật khẩu | Chuyển sang trang đổi mật khẩu |

### 1.3 Token hết hạn khi socket đang mở

Token chỉ kiểm tra **lúc kết nối**. Access token sống 15 phút nhưng cuộc họp có thể dài hơn, nên socket **không** bị ngắt khi token hết hạn. Việc thu hồi quyền được xử lý chủ động:

| Tình huống | Server làm |
|---|---|
| Admin khóa tài khoản | Gửi `force_disconnect` (`ACCOUNT_DISABLED`) rồi ngắt mọi socket của user |
| Người dùng `logout-all` / đổi mật khẩu / admin `revoke-sessions` | Gửi `force_disconnect` (`SESSIONS_REVOKED`) và ngắt socket |
| Mạng rớt, socket tự kết nối lại | Kết nối lại phải xác thực lại bằng token **hiện hành**, client cần refresh token trước khi `socket.connect()` lại |

Đây là đánh đổi có chủ ý, ghi ở `06-decisions.md` D15.

## 2. Quy ước sự kiện

- Tên sự kiện `snake_case`; dữ liệu là một object JSON.
- Client → server dùng **ack callback**:
  ```js
  socket.emit("join_room", { code, password }, (res) => { /* res.ok */ });
  ```
  - Thành công: `{ "ok": true, "data": { ... } }`
  - Thất bại: `{ "ok": false, "error": { "code": "ROOM_FULL", "message": "..." } }`
- Server → client là sự kiện một chiều, không ack.
- **`peer_id` = `sid` của Socket.io** (định danh một kết nối). `user_id` là định danh người dùng. Signaling dùng `peer_id`; phân quyền dùng `user_id`.
- Mọi handler (trừ `join_room`) kiểm tra: socket đang ở trong phòng (`NOT_IN_ROOM`), payload hợp lệ (`INVALID_PAYLOAD`), chưa vượt rate limit (`RATE_LIMITED`).

## 3. Mô hình dữ liệu trong RAM (`realtime/state.py`)

```python
Peer:  peer_id(sid), user_id, display_name, is_guest, joined_at,
       media: {audio: bool, video: bool, screen: bool}, hand_raised: bool

Room:  code, db_id, owner_id, mode, max_participants,
       peers: dict[peer_id, Peer],
       banned_user_ids: set[user_id],       # bị kick, không vào lại được tới khi phòng đóng
       empty_since: datetime | None,
       lock: asyncio.Lock                   # tuần tự hóa join/leave của phòng này
```

Truy cập qua giao diện `RoomStateStore` (`get_room`, `add_peer`, `remove_peer`...). v1 cài đặt trong bộ nhớ; có thể thay bằng Redis mà không sửa handler (`06-decisions.md` D05).

> **Ràng buộc quan trọng:** vì trạng thái nằm trong RAM của một process, **chỉ chạy Uvicorn với `--workers 1`** và một container `app`. Restart app sẽ làm mọi người rớt khỏi phòng và phải join lại (phòng trong DB vẫn `active`).

## 4. Phân quyền

| Vai trò | Xác định bởi | Làm được |
|---|---|---|
| **Thành viên** | Đã `join_room` | Signaling, chat, `media_state`, `raise_hand`, rời phòng |
| **Host** | `user_id == room.owner_id` đang có mặt; nếu owner vắng, host tạm là **người đăng nhập (không phải khách) vào phòng sớm nhất**, nếu không có thì khách vào sớm nhất | Thêm: `kick`, `mute_peer`, `close_room`, `transfer_host` |
| **Admin** | `role = admin` | Qua HTTP admin API (đóng phòng, kick) |

- Owner quay lại phòng thì **lấy lại quyền host** và phát `host_changed`.
- Mọi lệnh đặc quyền kiểm tra `is_host(room, user_id)` **trên server**, không tin client.
- Host không thể kick chính mình; không thể kick/mute admin đang ở trong phòng (admin có thể vào phòng để giám sát).

## 5. Sự kiện client → server

### 5.1 `join_room`

```json
{ "code": "abc-defg-hij", "password": "1234" }
```

Server (trong `room.lock`):
1. `maintenance_mode` chỉ chặn **tạo phòng**, không chặn vào phòng đang có → bỏ qua.
2. Phòng không có trong DB → `ROOM_NOT_FOUND`; `status = closed` → `ROOM_CLOSED`.
3. `user_id` nằm trong `banned_user_ids` → `BANNED`.
4. Phòng có mật khẩu: kiểm tra (argon2 verify). Sai → `WRONG_PASSWORD`. Giới hạn **5 lần sai / 5 phút / user+IP** → `RATE_LIMITED`.
5. Số peer ≥ `min(room.max_participants, max_participants_per_room)` → `ROOM_FULL`. Khi thay tab của cùng người dùng, chỗ của tab cũ được dùng lại.
6. Cùng `user_id` đã ở phòng này bằng `sid` khác (mở hai tab) → **tab cũ bị đá** (`kicked` với `reason = "SESSION_REPLACED"`), tab mới vào.
7. Một socket chỉ ở **một phòng tại một thời điểm**; đang ở phòng khác → `ALREADY_IN_ROOM`.
8. Thành công: `sio.enter_room(sid, code)`, thêm `Peer`, xóa `empty_since`.

Ack thành công:
```json
{
  "ok": true,
  "data": {
    "room": { "code": "abc-defg-hij", "name": "Họp nhóm", "mode": "meeting", "max_participants": 4, "host_peer_id": "sidA" },
    "you": { "peer_id": "sidN", "user_id": "uuid", "display_name": "An", "is_host": false },
    "peers": [
      { "peer_id": "sidA", "user_id": "uuid", "display_name": "Bình", "is_guest": false,
        "media": { "audio": true, "video": true, "screen": false }, "hand_raised": false }
    ],
    "media_policy": { "max_video_bitrate_kbps": 1500, "max_screen_bitrate_kbps": 2500, "max_video_resolution": "720p", "default_codec": "VP8" },
    "features": { "chat": true, "screen_share": true }
  }
}
```

Sau đó server phát `peer_joined` cho những người đã ở trong phòng.

### 5.2 `leave_room`
Không dữ liệu. Server gỡ peer, phát `peer_left` (`reason: "left"`). Ack `{ok: true}`.

### 5.3 `offer` / `answer` / `ice_candidate`

```json
{ "to": "<peer_id>", "sdp": { "type": "offer", "sdp": "v=0..." } }
{ "to": "<peer_id>", "sdp": { "type": "answer", "sdp": "v=0..." } }
{ "to": "<peer_id>", "candidate": { "candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0 } }
```

Server **chỉ chuyển tiếp**, không đọc/sửa nội dung, nhưng kiểm tra:
- Người gửi đang ở một phòng; `to` **ở cùng phòng đó** (chống gửi dữ liệu rác cho người lạ) → nếu không, `PEER_NOT_FOUND`.
- Kích thước `sdp` ≤ 20 KB; `candidate` ≤ 2 KB.
- Rate limit: ICE candidate tối đa 200 / 10 giây / socket.

Server gửi cho `to` cùng sự kiện, thay `to` bằng `from`: `{ "from": "<peer_id>", "sdp": ... }`.

### 5.4 `media_state`
```json
{ "audio": false, "video": true, "screen": false, "screen_stream_id": null }
```
Thông báo trạng thái bật/tắt của chính mình để UI người khác hiển thị icon. Đây chỉ là **thông tin hiển thị**; việc tắt thật là do client ngừng gửi track.

`screen_stream_id`: id của `MediaStream` chia sẻ màn hình, để bên nhận phân biệt luồng màn hình với luồng camera.

### 5.5 `chat_message`
```json
{ "text": "Chào mọi người" }
```
- Kiểm tra: `chat_enabled`, độ dài 1-2000 sau khi trim, **không HTML** (client tự `textContent`, không `innerHTML`).
- Rate limit: 5 tin / 3 giây / socket.
- Server gán `id`, `ts`, tên người gửi rồi broadcast `chat_message` cho **cả phòng (kể cả người gửi)**, rồi lưu DB bằng tác vụ nền nếu `chat_history_enabled`.

### 5.6 `raise_hand`
`{ "raised": true }` → broadcast `hand_changed`.

### 5.7 Sự kiện đặc quyền (chỉ host)

| Event | Dữ liệu | Tác dụng |
|---|---|---|
| `kick` | `{ "peer_id", "reason"? }` | Đá người ra khỏi phòng, **cấm vào lại** tới khi phòng đóng |
| `mute_peer` | `{ "peer_id", "kind": "audio" \| "video" }` | Gửi `force_mute` cho người đó |
| `transfer_host` | `{ "peer_id" }` | Chọn host tạm trong số người dùng đã đăng nhập. Khi owner đang có mặt, quyền của host tạm bắt đầu lúc owner rời phòng. |
| `close_room` | không | Đóng phòng (tương đương `DELETE /rooms/{code}`) |

Không phải host → ack `{ok: false, error: {code: "NOT_ROOM_HOST"}}`. Các sự kiện này gọi **cùng hàm trong `room_service`** mà HTTP admin API cũng gọi, nên không viết logic hai lần.

## 6. Sự kiện server → client

| Event | Dữ liệu | Gửi cho | Khi nào |
|---|---|---|---|
| `peer_joined` | `{ peer }` | Cả phòng (trừ người mới) | Có người vào |
| `peer_left` | `{ peer_id, reason }` | Cả phòng | `reason`: `left`, `disconnected`, `kicked`, `session_replaced` |
| `offer` | `{ from, sdp }` | 1 peer | Chuyển tiếp |
| `answer` | `{ from, sdp }` | 1 peer | Chuyển tiếp |
| `ice_candidate` | `{ from, candidate }` | 1 peer | Chuyển tiếp |
| `chat_message` | `{ id, from: {peer_id, user_id, display_name}, text, ts }` | Cả phòng | Có tin nhắn |
| `media_state` | `{ peer_id, audio, video, screen, screen_stream_id }` | Cả phòng (trừ người gửi) | Ai đó đổi trạng thái |
| `hand_changed` | `{ peer_id, raised }` | Cả phòng | |
| `force_mute` | `{ kind, by_peer_id }` | 1 peer | Host mute |
| `host_changed` | `{ host_peer_id }` | Cả phòng | Owner vào/ra, `transfer_host`, host rời |
| `kicked` | `{ reason }` | Người bị kick | Trước khi bị đưa ra khỏi phòng |
| `room_closed` | `{ reason }` | Cả phòng | Host/admin đóng, hoặc timeout; sau đó mọi người bị đưa ra khỏi phòng |
| `server_notice` | `{ code, message }` | Cả phòng hoặc 1 người | Thông báo từ server |
| `force_disconnect` | `{ reason }` | 1 user (mọi socket) | Bị khóa, thu hồi phiên; ngay sau đó server ngắt kết nối |

## 7. Luồng chi tiết

### 7.1 Vào phòng và thiết lập kết nối (mesh)

**Quy tắc: người mới vào là bên gửi `offer` cho từng người đang ở trong phòng.** Người cũ chỉ chờ `offer` rồi trả `answer`. Quy tắc này tránh "glare" (hai bên cùng gửi offer một lúc).

```
Mới (N)               Server                      Cũ (E)
  |-- GET /turn-credentials (HTTP) -->            |
  |-- join_room {code, password} ->|              |
  |                                | kiểm tra: phòng, mật khẩu, ban, sức chứa
  |<-- ack {room, you, peers:[E]} -|              |
  |                                |-- peer_joined {N} --------->|
  |  (với mỗi peer trong `peers`: tạo RTCPeerConnection, addTrack, createOffer)
  |-- offer {to:E, sdp} ---------->|-- offer {from:N, sdp} ----->|
  |                                |   (E tạo PC, addTrack, setRemoteDescription, createAnswer)
  |                                |<-- answer {to:N, sdp} ------|
  |<-- answer {from:E, sdp} -------|                             |
  |<====== ice_candidate hai chiều, qua server =================>|
  |<================ media P2P (SRTP) ==========================>|
        (P2P thất bại → ICE chọn relay qua TURN)
```

Lưu ý khi viết client:
- ICE candidate có thể đến **trước** khi `setRemoteDescription` xong: bỏ vào hàng đợi, nạp sau.
- `iceServers` lấy từ `/turn-credentials` **trước** khi tạo `RTCPeerConnection`.
- Áp dụng `media_policy` bằng `RTCRtpSender.setParameters()` (`maxBitrate`) và `getUserMedia` constraints.

### 7.2 Đàm phán lại (bật chia sẻ màn hình, đổi camera)

Thêm/bỏ track làm trình duyệt bắn `negotiationneeded`, và **bất kỳ bên nào** cũng có thể gửi `offer` mới. Dùng mẫu **"perfect negotiation"** của WebRTC để xử lý va chạm:

- `polite = (my_peer_id > their_peer_id)` (so sánh chuỗi): hai bên tự xác định mà không cần server.
- Khi nhận `offer` mà đang có offer của chính mình hoặc `signalingState != "stable"`:
  - Bên **impolite**: bỏ qua offer nhận được.
  - Bên **polite**: rollback offer của mình, chấp nhận offer nhận được.

```
Share màn hình (A):
  A: getDisplayMedia → addTrack → negotiationneeded
  A -- offer {to:B} --> Server -- offer {from:A} --> B
  B -- answer {to:A} -> Server -- answer {from:B} -> A
  A -- media_state {screen:true, screen_stream_id} --> cả phòng
```

### 7.3 Rời phòng và mất kết nối

| Tình huống | Server làm |
|---|---|
| `leave_room` | Gỡ peer, phát `peer_left (left)` |
| Socket ngắt (đóng tab, rớt mạng quá `ping_timeout`) | Handler `disconnect` gỡ peer khỏi mọi phòng, phát `peer_left (disconnected)` |
| Đổi mạng ngắn (Wi-Fi → 4G) nhưng socket vẫn sống | Client gọi `pc.restartIce()`, gửi `offer` mới với `iceRestart` qua cùng luồng |
| Socket kết nối lại (sid mới) | Với server đây là **người mới**: client phải `join_room` lại và dựng lại các `RTCPeerConnection` |

Tham số Socket.io: `ping_interval = 25s`, `ping_timeout = 20s` (mặc định). Chưa làm "thời gian chờ nối lại giữ chỗ"; ghi vào danh sách cải tiến.

Khi phòng hết người: đặt `empty_since = now`. Nếu không ai vào lại trong `room_empty_ttl_seconds` → đóng phòng (`closed_reason = empty_timeout`), cập nhật DB, xóa khỏi RAM. Một tác vụ nền quét mỗi 30 giây.

### 7.4 Kick

```
Host              Server                Người bị kick (T)      Còn lại
 |-- kick {T} ---->|
 |                 | kiểm tra host; T ở trong phòng; T không phải admin
 |                 |-- kicked {reason} ------>|
 |                 | gỡ T khỏi phòng, thêm user_id vào banned_user_ids
 |                 |-- peer_left {T, kicked} ----------------->|
 |<-- ack {ok} ----|
```
Client của T tự đóng các `RTCPeerConnection` khi nhận `kicked`.

### 7.5 Admin khóa tài khoản đang trong phòng

```
Admin (HTTP) PATCH /admin/users/{id} {is_active:false}
  → user_service: cập nhật DB + thu hồi refresh token + ghi audit (1 transaction)
  → realtime: force_disconnect → gỡ khỏi phòng (peer_left) → disconnect socket
```

### 7.6 Đóng phòng

`close_room` (host), `DELETE /rooms/{code}` hoặc `DELETE /admin/rooms/{code}` đều đi qua `room_service.close_room()`:
1. Cập nhật DB: `status = closed`, `closed_reason`, `closed_at`.
2. Phát `room_closed` cho cả phòng.
3. Đưa mọi socket ra khỏi room Socket.io, xóa `Room` khỏi RAM.

## 8. Mã lỗi socket

| Code | Khi nào |
|---|---|
| `INVALID_PAYLOAD` | Thiếu/sai kiểu trường, quá kích thước |
| `NOT_IN_ROOM` | Gửi sự kiện phòng khi chưa join |
| `ALREADY_IN_ROOM` | Join khi đang ở phòng khác |
| `ROOM_NOT_FOUND`, `ROOM_CLOSED` | |
| `ROOM_FULL` | Hết chỗ |
| `WRONG_PASSWORD` | Sai mật khẩu phòng |
| `BANNED` | Từng bị kick khỏi phòng này |
| `PEER_NOT_FOUND` | `to` không ở cùng phòng |
| `NOT_ROOM_HOST` | Dùng lệnh đặc quyền không phải host |
| `CHAT_DISABLED` | `chat_enabled = false` |
| `RATE_LIMITED` | Gửi quá nhanh |
| `INTERNAL_ERROR` | Lỗi server (có `request_id`) |

Lặp lại vi phạm rate limit nhiều lần liên tiếp (ví dụ 5 lần trong 1 phút) → server ngắt kết nối socket đó.

## 9. Giai đoạn SFU và livestream (A10, phác thảo)

Giữ nguyên các sự kiện ở trên, thay đổi chính:
- Thay vì mesh, mỗi client chỉ có **một** `RTCPeerConnection` tới server (SFU). `offer/answer/ice_candidate` dùng `to: "sfu"`.
- Thêm `track_published` / `track_unpublished` (server → client) để client biết có luồng mới cần subscribe; thêm `subscribe` / `unsubscribe` (client → server).
- Phòng `mode = livestream`: chỉ host (và người được `promote_speaker`) được publish; người xem chỉ nhận. Thêm `promote_speaker` / `demote_speaker` (host).
- Chi tiết sẽ viết thêm khi bắt đầu A10, sau khi đã chạy được mesh. Cần kiểm chứng giới hạn của aiortc (xem `06-decisions.md` Q4).

## 10. Chỉ số theo dõi (cho `/metrics`)

| Metric | Loại |
|---|---|
| `socket_connections` | gauge |
| `rooms_active` | gauge |
| `room_participants` (label: không dùng `code`) | histogram / tổng gauge |
| `socket_events_total{event}` | counter |
| `socket_errors_total{code}` | counter |
| `room_joins_total`, `room_kicks_total`, `rooms_created_total` | counter |
| `join_room_duration_seconds` | histogram |

Không đặt `room code` hay `user_id` làm label Prometheus (số lượng giá trị quá lớn, làm nặng Prometheus).

## 11. Kiểm thử

| Loại | Cách làm |
|---|---|
| Unit | `RoomStateStore`, hàm kiểm tra quyền host, logic chọn host tạm |
| Integration | Dựng app thật, dùng `socketio.AsyncClient` tạo 2-3 client: join, signaling chuyển tiếp đúng người, phòng đầy, sai mật khẩu, kick + cấm vào lại, admin khóa user ngắt socket, rate limit |
| Thủ công | 2 tab trình duyệt; sau đó 2 thiết bị khác mạng (4G + Wi-Fi) để buộc đi qua TURN |
