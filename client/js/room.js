import { accessToken, api, clearSession, requireSession } from "./api.js";
import { element, message, onForm } from "./ui.js";
import { PeerCall } from "./webrtc.js";

const code = new URLSearchParams(location.search).get("code") || "";
let active;

class RoomCall {
  constructor(password) {
    this.password = password;
    this.accepted = false;
    this.stopped = false;
    this.policy = {};
    this.socket = window.io({
      autoConnect: false,
      transports: ["websocket"],
      timeout: 6000,
      auth: done => accessToken().then(token => done({token}), error => {
        done({});
        this.fail(error);
      }),
    });
    this.socket.on("connect", () => this.join());
    this.socket.on("connect_error", error => {
      if (this.accepted && this.socket.active) return;
      this.fail(new Error(error.data?.message || error.message || "Không thể kết nối tới phòng."));
    });
    this.socket.on("disconnect", () => {
      if (!this.stopped) {
        this.resetPeer();
        message("Mất kết nối. Đang nối lại…");
      }
    });
    this.socket.on("peer_joined", ({peer}) => {
      if (this.remoteId && this.remoteId !== peer.peer_id) return;
      this.remoteId = peer.peer_id;
      element("remote-name").textContent = peer.display_name;
    });
    this.socket.on("peer_left", ({peer_id: id}) => {
      if (id === this.remoteId) {
        this.resetPeer();
        message("Người kia đã rời phòng.");
      }
    });
    this.socket.on("offer", message => this.receive(message, "sdp"));
    this.socket.on("answer", message => this.receive(message, "sdp"));
    this.socket.on("ice_candidate", message => this.receive(message, "candidate"));
    this.socket.on("kicked", ({reason}) => this.end(
      reason === "SESSION_REPLACED" ? "Một tab khác đã vào phòng bằng tài khoản này." : "Bạn đã bị đưa ra khỏi phòng."
    ));
    this.socket.on("room_closed", () => this.end("Phòng đã đóng."));
    this.socket.on("force_disconnect", () => {
      clearSession();
      this.end("Phiên cuộc gọi đã bị thu hồi. Vui lòng đăng nhập lại.");
    });
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      throw new Error("Trình duyệt cần hỗ trợ camera và WebRTC tại localhost hoặc HTTPS.");
    }
    await this.loadIceServers();
    if (this.stopped) return;
    this.local = await navigator.mediaDevices.getUserMedia({
      audio: true, video: {width: {ideal: 1280}, height: {ideal: 720}},
    });
    element("local").srcObject = this.local;
    const connected = new Promise((resolve, reject) => {
      this.firstJoin = {resolve, reject};
    });
    this.socket.connect();
    return connected;
  }

  async loadIceServers() {
    let data;
    try {
      data = await api("/turn-credentials", {authenticated: true});
    } catch (error) {
      if (error.code !== "GUEST_NOT_ALLOWED") throw error;
      data = {urls: [], ttl: 0};
    }
    if (this.stopped) return;

    const stun = data.urls.filter(url => /^stuns?:/.test(url));
    const turn = data.urls.filter(url => /^turns?:/.test(url));
    const iceServers = stun.length ? [{urls: stun}] : [];
    if (turn.length && data.username && data.credential) {
      iceServers.push({urls: turn, username: data.username, credential: data.credential});
    }
    this.iceServers = iceServers;
    this.peer?.updateIceServers(iceServers);
    if (data.ttl > 0) {
      this.iceRefresh = setTimeout(() => this.refreshIceServers(), (data.ttl - 60) * 1000);
    }
  }

  async refreshIceServers() {
    try {
      await this.loadIceServers();
    } catch (error) {
      if (!this.stopped && (!error.status || error.status === 429 || error.status >= 500)) {
        this.iceRefresh = setTimeout(() => this.refreshIceServers(), 30000);
      }
    }
  }

  async emit(event, payload) {
    if (!this.socket.connected) throw new Error("Kết nối phòng đang gián đoạn.");
    const result = await this.socket.timeout(6000).emitWithAck(event, payload);
    if (!result?.ok) throw new Error(result?.error?.message || "Không thể xử lý sự kiện phòng.");
    return result.data;
  }

  async join() {
    try {
      const info = await this.emit("join_room", {code, password: this.password || null});
      if (this.stopped) return;
      if (info.peers.length > 1) {
        throw new Error("Trình duyệt này hỗ trợ cuộc gọi một đối một.");
      }
      this.policy = info.media_policy;
      this.accepted = true;
      element("join-panel").hidden = true;
      element("call-panel").hidden = false;
      const track = this.local.getVideoTracks()[0];
      const maxHeight = parseInt(this.policy.max_video_resolution, 10);
      if (track && Number.isFinite(maxHeight)) {
        const height = Math.min(maxHeight, 720);
        track.applyConstraints({
          width: {ideal: Math.round(height * 16 / 9)},
          height: {ideal: height, max: maxHeight},
          frameRate: {ideal: 30},
        }).catch(() => {});
      }
      if (info.peers.length === 1) {
        const other = info.peers[0];
        element("remote-name").textContent = other.display_name;
        this.makePeer(other.peer_id, true);
      }
      message(this.remoteId ? "Đang kết nối video…" : "Đang chờ người tham gia.");
      this.firstJoin?.resolve();
      this.firstJoin = null;
    } catch (error) {
      this.fail(error);
    }
  }

  makePeer(id, initiates) {
    this.remoteId = id;
    this.peer = new PeerCall({
      id,
      initiates,
      polite: this.socket.id > id,
      local: this.local,
      policy: this.policy,
      iceServers: this.iceServers,
      signal: (event, payload) => this.emit(event, {to: id, ...payload}),
      showStream: stream => {
        const video = element("remote");
        if (video.srcObject !== stream) video.srcObject = stream;
        playRemote();
      },
      showState: state => {
        if (state === "connected") message("Đã kết nối video.");
        if (state === "failed") message("Không kết nối được luồng video. Thử rời phòng rồi vào lại.", true);
      },
      showError: error => message(error.message || "Kết nối video gặp lỗi.", true),
    });
    return this.peer;
  }

  receive({from, ...payload}, kind) {
    if (this.stopped || !this.local || (this.remoteId && from !== this.remoteId)) return;
    const peer = this.peer || this.makePeer(from, false);
    if (kind === "sdp") peer.receiveDescription(payload.sdp);
    else peer.receiveCandidate(payload.candidate);
  }

  resetPeer() {
    this.peer?.close();
    this.peer = null;
    this.remoteId = null;
    element("remote").srcObject = null;
    element("play-remote").hidden = true;
    element("remote-name").textContent = "Đang chờ người tham gia";
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    clearTimeout(this.iceRefresh);
    this.socket.disconnect();
    this.resetPeer();
    this.local?.getTracks().forEach(track => track.stop());
    element("local").srcObject = null;
    this.password = null;
  }

  fail(error) {
    if (this.stopped) return;
    const initial = this.firstJoin;
    this.firstJoin = null;
    this.stop();
    if (initial) initial.reject(error);
    else {
      element("call-panel").hidden = true;
      element("join-panel").hidden = false;
      message(error.message, true);
    }
  }

  end(text) {
    this.firstJoin?.reject(new Error(text));
    this.firstJoin = null;
    this.stop();
    element("join-panel").hidden = true;
    element("call-panel").hidden = true;
    message(text, true);
  }

  async leave() {
    try {
      if (this.accepted && this.socket.connected) await this.emit("leave_room");
    } finally {
      this.stop();
      location.assign("/lobby");
    }
  }
}

onForm("enter-form", async (fields, form) => {
  active?.stop();
  const call = active = new RoomCall(fields.password);
  const mic = element("mic");
  const camera = element("camera");
  mic.textContent = "Mic bật";
  camera.textContent = "Camera bật";
  mic.setAttribute("aria-pressed", "true");
  camera.setAttribute("aria-pressed", "true");
  try {
    await call.start();
    form.reset();
  } catch (error) {
    call.stop();
    if (error.name === "NotAllowedError") throw new Error("Hãy cho phép trang dùng camera và mic.");
    if (error.name === "NotFoundError") throw new Error("Không tìm thấy camera hoặc mic.");
    throw error;
  }
});

for (const [button, kind, label] of [["mic", "audio", "Mic"], ["camera", "video", "Camera"]]) {
  element(button).addEventListener("click", event => {
    const tracks = active?.local?.getTracks().filter(track => track.kind === kind);
    if (!tracks?.length) return;
    const enabled = !tracks[0].enabled;
    tracks.forEach(track => { track.enabled = enabled; });
    event.currentTarget.setAttribute("aria-pressed", String(enabled));
    event.currentTarget.textContent = label + (enabled ? " bật" : " tắt");
  });
}
element("leave").addEventListener("click", () => active?.leave().catch(() => {}));
element("play-remote").addEventListener("click", playRemote);
window.addEventListener("pagehide", () => active?.stop());

async function playRemote() {
  const video = element("remote");
  const stream = video.srcObject;
  try {
    await video.play();
    element("play-remote").hidden = true;
  } catch {
    if (stream && video.srcObject === stream) element("play-remote").hidden = false;
  }
}

element("copy-code").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(code);
    message("Đã sao chép mã phòng.");
  } catch {
    message("Mã phòng: " + code);
  }
});

if (requireSession()) {
  try {
    if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(code)) throw new Error("Mã phòng không hợp lệ.");
    const room = await api("/rooms/" + code, {authenticated: true});
    element("room-name").textContent = room.name || "Phòng gọi";
    element("room-code").textContent = "Mã phòng " + room.code;
    if (room.status === "closed") throw new Error("Phòng đã đóng.");
    element("copy-code").hidden = false;
    element("password-label").hidden = !room.has_password;
    element("enter-form").elements.password.required = room.has_password;
    element("join-panel").hidden = false;
  } catch (error) {
    if (error.status === 401) location.replace("/");
    else message(error.message, true);
  }
}
