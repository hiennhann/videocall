import { accessToken, api, clearSession, requireSession } from "./api.js";
import { element, message, onForm } from "./ui.js";
import { PeerCall } from "./webrtc.js";

const code = new URLSearchParams(location.search).get("code") || "";
const mediaButtons = {audio: ["mic", "Mic"], video: ["camera", "Camera"]};
let active;

class RoomCall {
  constructor(password) {
    this.password = password;
    this.accepted = false;
    this.joined = false;
    this.stopped = false;
    this.policy = {};
    this.features = {};
    this.remoteStreams = new Map();
    this.chatIds = new Set();
    element("chat-messages").replaceChildren();
    element("older-messages").hidden = true;
    chatError();
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
        this.joined = false;
        this.stopScreen();
        this.resetPeer();
        message("Mất kết nối. Đang nối lại…");
      }
    });
    this.socket.on("peer_joined", ({peer}) => {
      if (this.remoteId && this.remoteId !== peer.peer_id) return;
      this.remoteId = peer.peer_id;
      element("remote-name").textContent = peer.display_name;
      this.setRemoteMedia(peer.media);
      this.renderControls();
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
    this.socket.on("chat_message", ({id, from, text}) => {
      this.addMessages([{id, sender_name: from.display_name, content: text}]);
    });
    this.socket.on("media_state", media => {
      if (media.peer_id === this.remoteId) this.setRemoteMedia(media);
    });
    this.socket.on("host_changed", ({host_peer_id}) => {
      this.hostId = host_peer_id;
      this.renderControls();
    });
    this.socket.on("force_mute", ({kind}) => {
      this.setTrack(kind, false);
      message(kind === "audio" ? "Host đã tắt mic của bạn." : "Host đã tắt camera của bạn.");
    });
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
      this.features = info.features;
      this.hostId = info.room.host_peer_id;
      this.accepted = true;
      this.joined = true;
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
        this.remoteId = other.peer_id;
        element("remote-name").textContent = other.display_name;
        this.setRemoteMedia(other.media);
        if (!this.peer) this.makePeer(other.peer_id, true);
      }
      this.renderControls();
      this.publishMedia().catch(error => message(error.message, true));
      this.loadHistory();
      message(this.remoteId ? "Đang kết nối video…" : "Đang chờ người tham gia.");
      this.firstJoin?.resolve();
      this.firstJoin = null;
    } catch (error) {
      this.fail(error);
    }
  }

  renderControls() {
    const canMute = this.joined && this.remoteId && this.hostId === this.socket.id;
    for (const kind of Object.keys(mediaButtons)) element("mute-peer-" + kind).hidden = !canMute;
    element("screen").hidden = !this.joined || !this.features.screen_share;
    element("chat-form").hidden = !this.joined || !this.features.chat;
  }

  publishMedia() {
    if (!this.joined) return Promise.resolve();
    return this.emit("media_state", {
      audio: Boolean(this.local.getAudioTracks()[0]?.enabled),
      video: Boolean(this.local.getVideoTracks()[0]?.enabled),
      screen: Boolean(this.screen),
      screen_stream_id: this.screen ? this.screenStream.id : null,
    });
  }

  setTrack(kind, enabled) {
    const track = this.local?.getTracks().find(track => track.kind === kind);
    if (!track) return;
    track.enabled = enabled ?? !track.enabled;
    const [button, label] = mediaButtons[kind];
    element(button).setAttribute("aria-pressed", String(track.enabled));
    element(button).textContent = label + (track.enabled ? " bật" : " tắt");
    this.publishMedia().catch(error => message(error.message, true));
  }

  async toggleScreen() {
    if (this.screen) {
      this.stopScreen();
      return;
    }
    if (!this.joined || !this.features.screen_share) return;
    if (!navigator.mediaDevices.getDisplayMedia) {
      throw new Error("Trình duyệt chưa hỗ trợ chia sẻ màn hình.");
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({video: true, audio: false});
    const track = stream.getVideoTracks()[0];
    if (!this.joined || track.readyState === "ended") {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    this.screen = stream;
    this.screenStream ??= new MediaStream();
    track.addEventListener("ended", () => {
      if (this.screen === stream) this.stopScreen();
    }, {once: true});
    try {
      await this.publishMedia();
      if (this.screen !== stream) return;
      await this.peer?.setScreen(this.screenStream, track);
      if (this.screen === stream) this.renderLocalScreen();
    } catch (error) {
      if (this.screen === stream) this.stopScreen();
      throw error;
    }
  }

  stopScreen() {
    if (!this.screen) return;
    this.screen.getTracks().forEach(track => track.stop());
    this.screen = null;
    this.peer?.setScreen(null).catch(error => message(error.message, true));
    this.renderLocalScreen();
    this.publishMedia().catch(error => message(error.message, true));
  }

  renderLocalScreen() {
    const button = element("screen");
    element("local-screen").srcObject = this.screen;
    element("local-screen-panel").hidden = !this.screen;
    button.setAttribute("aria-pressed", String(Boolean(this.screen)));
    button.textContent = this.screen ? "Dừng chia sẻ" : "Chia sẻ màn hình";
  }

  setRemoteMedia(media) {
    this.remoteMedia = media;
    element("remote-media").textContent = [
      media.audio ? "Mic bật" : "Mic tắt",
      media.video ? "Camera bật" : "Camera tắt",
      ...(media.screen ? ["Đang chia sẻ màn hình"] : []),
    ].join(" · ");
    this.renderRemote();
  }

  renderRemote() {
    const camera = [...this.remoteStreams.values()].find(stream => stream.getAudioTracks().length);
    const remote = element("remote");
    if (camera && remote.srcObject !== camera) {
      remote.srcObject = camera;
      playRemote();
    }
    const screen = this.remoteStreams.get(this.remoteMedia?.screen_stream_id);
    element("remote-screen-panel").hidden = !screen;
    if (element("remote-screen").srcObject !== (screen ?? null)) {
      element("remote-screen").srcObject = screen ?? null;
    }
  }

  addMessages(entries, older = false) {
    const list = element("chat-messages");
    const height = list.scrollHeight;
    const atBottom = height - list.scrollTop - list.clientHeight < 24;
    for (const entry of entries) {
      if (this.chatIds.has(entry.id)) continue;
      this.chatIds.add(entry.id);
      const item = document.createElement("li");
      item.dataset.id = entry.id;
      const name = document.createElement("strong");
      name.textContent = entry.sender_name;
      item.append(name, " · " + entry.content);
      const next = [...list.children].find(node => Number(node.dataset.id) > entry.id);
      list.insertBefore(item, next ?? null);
    }
    if (older) list.scrollTop += list.scrollHeight - height;
    else if (atBottom) list.scrollTop = list.scrollHeight;
  }

  async loadHistory(before) {
    const sid = this.socket.id;
    const button = element("older-messages");
    const query = before ? "?before=" + before : "";
    button.disabled = true;
    try {
      const history = await api("/rooms/" + code + "/messages" + query, {authenticated: true});
      if (!this.joined || sid !== this.socket.id) return;
      this.addMessages(history.items, Boolean(before));
      this.beforeMessage = history.next_before;
      button.hidden = !this.beforeMessage;
    } catch (error) {
      if (this.joined && sid === this.socket.id) chatError(error.message);
    } finally {
      if (sid === this.socket.id) button.disabled = false;
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
        this.remoteStreams.set(stream.id, stream);
        this.renderRemote();
      },
      showState: state => {
        if (state === "connected") message("Đã kết nối video.");
        if (state === "failed") message("Không kết nối được luồng video. Thử rời phòng rồi vào lại.", true);
      },
      showError: error => message(error.message || "Kết nối video gặp lỗi.", true),
    });
    if (this.screen) {
      this.peer.setScreen(this.screenStream, this.screen.getVideoTracks()[0])
        .catch(error => message(error.message, true));
    }
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
    this.remoteMedia = null;
    this.remoteStreams.clear();
    element("remote").srcObject = null;
    element("remote-media").textContent = "";
    this.renderRemote();
    element("play-remote").hidden = true;
    element("remote-name").textContent = "Đang chờ người tham gia";
    this.renderControls();
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.joined = false;
    clearTimeout(this.iceRefresh);
    this.socket.disconnect();
    this.stopScreen();
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

for (const [kind, [button]] of Object.entries(mediaButtons)) {
  element(button).addEventListener("click", () => active?.setTrack(kind));
  element("mute-peer-" + kind).addEventListener("click", async () => {
    if (!active?.remoteId) return;
    try {
      await active.emit("mute_peer", {peer_id: active.remoteId, kind});
    } catch (error) {
      message(error.message, true);
    }
  });
}
element("screen").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await active?.toggleScreen();
  } catch (error) {
    if (error.name !== "NotAllowedError") message(error.message, true);
  } finally {
    button.disabled = false;
  }
});
onForm("chat-form", async ({text}, form) => {
  chatError();
  try {
    await active.emit("chat_message", {text});
    form.reset();
  } catch (error) {
    chatError(error.message);
  }
});
element("older-messages").addEventListener("click", () => active?.loadHistory(active.beforeMessage));

function chatError(text = "") {
  const notice = element("chat-error");
  notice.textContent = text;
  notice.hidden = !text;
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
