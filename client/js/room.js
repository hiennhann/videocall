import { accessToken, api, clearSession, requireSession } from "./api.js";
import { LiveConnection } from "./live.js";
import { PeerTile } from "./peer-tile.js";
import { element, message, onForm } from "./ui.js";
import { PeerCall } from "./webrtc.js";

const code = new URLSearchParams(location.search).get("code") || "";
const mediaButtons = {audio: ["mic", "Mic"], video: ["camera", "Camera"]};
let active;
let roomMode;

class RoomCall {
  constructor(password) {
    this.password = password;
    this.mode = roomMode;
    this.liveMembers = new Map();
    this.accepted = false;
    this.joined = false;
    this.stopped = false;
    this.policy = {};
    this.features = {};
    this.peers = new Map();
    this.pendingEvents = [];
    this.statsVisible = false;
    element("stats-toggle").setAttribute("aria-pressed", "false");
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
        this.closeLive();
        this.liveMembers.clear();
        this.resetPeers();
        message("Mất kết nối. Đang nối lại…");
      }
    });
    this.roomEvent("peer_joined", ({peer}) => {
      if (this.mode === "livestream") this.liveMembers.set(peer.peer_id, peer);
      else this.makePeer(peer, false);
      this.renderControls();
      message("");
    });
    this.roomEvent("peer_left", ({peer_id: id}) => {
      this.liveMembers.delete(id);
      this.removePeer(id);
      if (this.mode === "livestream") this.renderControls();
      else if (!this.peers.size) message("Đang chờ người tham gia.");
    });
    this.roomEvent("live_speaker_changed", ({speaker_peer_id: id}) => {
      this.speaker = id;
      if (id !== this.socket.id && this.local) this.closeLive();
      this.renderControls();
    });
    this.roomEvent("track_published", ({peer_id: id}) => this.livePublisher(id));
    this.roomEvent("track_unpublished", ({peer_id: id}) => {
      if (id === this.publisher) this.livePublisher(null);
    });
    this.roomEvent("offer", ({from, sdp}) => this.peers.get(from)?.call.receiveDescription(sdp));
    this.roomEvent("answer", ({from, sdp}) => this.peers.get(from)?.call.receiveDescription(sdp));
    this.roomEvent("ice_candidate", ({from, candidate}) => this.peers.get(from)?.call.receiveCandidate(candidate));
    this.socket.on("chat_message", ({id, from, text}) => {
      this.addMessages([{id, sender_name: from.display_name, content: text}]);
    });
    this.roomEvent("media_state", media => {
      this.peers.get(media.peer_id)?.tile.updateMedia(media);
    });
    this.roomEvent("host_changed", ({host_peer_id}) => {
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

  roomEvent(event, handler) {
    this.socket.on(event, data => {
      if (this.stopped) return;
      if (this.joined) handler(data);
      else if (this.pendingEvents.length < 800) this.pendingEvents.push(() => handler(data));
    });
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      throw new Error("Trình duyệt cần hỗ trợ camera và WebRTC tại localhost hoặc HTTPS.");
    }
    await this.loadIceServers();
    if (this.stopped) return;
    if (this.mode !== "livestream") {
      this.local = await navigator.mediaDevices.getUserMedia({
        audio: true, video: {width: {ideal: 1280}, height: {ideal: 720}},
      });
    }
    if (this.stopped) {
      this.local?.getTracks().forEach(track => track.stop());
      return;
    }
    element("local").srcObject = this.local ?? null;
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
    for (const {call} of this.peers.values()) call.updateIceServers(iceServers);
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

  async emit(event, payload, timeout = 6000) {
    if (!this.socket.connected) throw new Error("Kết nối phòng đang gián đoạn.");
    const result = await this.socket.timeout(timeout).emitWithAck(event, payload);
    if (!result?.ok) throw new Error(result?.error?.message || "Không thể xử lý sự kiện phòng.");
    return result.data;
  }

  async join() {
    const sid = this.socket.id;
    try {
      const info = await this.emit("join_room", {code, password: this.password || null});
      if (this.stopped || this.socket.id !== sid) return;
      this.policy = info.media_policy;
      this.features = info.features;
      this.hostId = info.room.host_peer_id;
      this.speaker = info.room.speaker_peer_id;
      this.accepted = true;
      this.joined = true;
      element("join-panel").hidden = true;
      element("call-panel").hidden = false;
      element("live-panel").hidden = this.mode !== "livestream";
      const track = this.local?.getVideoTracks()[0];
      const maxHeight = parseInt(this.policy.max_video_resolution, 10);
      if (track && Number.isFinite(maxHeight)) {
        const height = Math.min(maxHeight, 720);
        track.applyConstraints({
          width: {ideal: Math.round(height * 16 / 9)},
          height: {ideal: height, max: maxHeight},
          frameRate: {ideal: 30},
        }).catch(() => {});
      }
      if (this.mode === "livestream") {
        this.liveMembers = new Map(info.peers.map(peer => [peer.peer_id, peer]));
        this.livePublisher(info.room.publisher_peer_id);
      } else {
        for (const peer of info.peers) this.makePeer(peer, true);
      }
      for (const handle of this.pendingEvents.splice(0)) handle();
      this.renderControls();
      this.publishMedia().catch(error => message(error.message, true));
      this.loadHistory();
      message(this.mode === "livestream" || this.peers.size ? "" : "Đang chờ người tham gia.");
      this.firstJoin?.resolve();
      this.firstJoin = null;
    } catch (error) {
      if (this.socket.id === sid) this.fail(error);
    }
  }

  renderControls() {
    const live = this.mode === "livestream";
    const canMute = this.joined && this.hostId === this.socket.id;
    for (const {tile} of this.peers.values()) tile.mute.hidden = !canMute;
    element("screen").hidden = !this.joined || !this.features.screen_share;
    element("chat-form").hidden = !this.joined || !this.features.chat;
    element("stats-toggle").hidden = live;
    element("local-panel").hidden = live && !this.local;
    for (const [button] of Object.values(mediaButtons)) element(button).hidden = live && !this.local;
    element("live-start").hidden = !live || !this.joined || this.speaker !== this.socket.id;
    element("live-start").textContent = this.local ? "Dừng phát" : "Bắt đầu phát";
    const form = element("live-speaker-form");
    form.hidden = !live || !canMute;
    if (!form.hidden) {
      const select = form.elements.peer_id;
      const selected = select.value || this.speaker;
      select.replaceChildren(
        new Option("Host", this.socket.id),
        ...[...this.liveMembers.values()].map(peer => new Option(peer.display_name, peer.peer_id)),
      );
      if ([...select.options].some(option => option.value === selected)) select.value = selected;
    }
  }

  publishMedia() {
    if (!this.joined || !this.local) return Promise.resolve();
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
      await this.setPeerScreens(track);
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
    this.setPeerScreens(null).catch(error => message(error.message, true));
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

  livePublisher(id) {
    if (id === this.publisher && this.liveConnection) return;
    this.publisher = id;
    element("live-retry").hidden = true;
    if (id === this.socket.id) return;
    this.closeLive();
    element("live-status").textContent = id ? "Đang kết nối livestream…" : "Đang chờ người phát.";
    if (id && this.joined) this.connectLive(false);
  }

  async connectLive(publishing) {
    const live = new LiveConnection(this.iceServers, publishing ? this.local : null, stream => {
      const video = element("live-video");
      video.srcObject = stream;
      video.hidden = false;
      playLive();
    }, state => {
      if (state === "connected") element("live-status").textContent = publishing ? "Đang phát." : "Đang xem livestream.";
      if (state === "failed" && this.liveConnection === live) {
        this.liveFailed(publishing, "Kết nối livestream thất bại.");
      }
    });
    this.liveConnection = live;
    try {
      await live.connect(sdp => publishing
        ? this.emit("offer", {to: "sfu", sdp}, 10000)
        : this.emit("subscribe", sdp, 10000));
    } catch (error) {
      if (live === this.liveConnection) this.liveFailed(publishing, error.message);
    }
  }

  liveFailed(publishing, description) {
    this.closeLive();
    if (publishing && this.joined) this.emit("unsubscribe").catch(() => {});
    element("live-status").textContent = description;
    element("live-retry").hidden = publishing || !this.publisher;
  }

  async toggleLive() {
    if (!this.joined || this.speaker !== this.socket.id) return;
    if (this.local) {
      this.closeLive();
      await this.emit("unsubscribe");
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true, video: {width: {ideal: 640}, height: {ideal: 360}, frameRate: {ideal: 15, max: 15}},
    });
    if (!this.joined || this.speaker !== this.socket.id) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    this.closeLive();
    this.local = stream;
    element("local").srcObject = stream;
    this.renderControls();
    element("live-status").textContent = "Đang bắt đầu phát…";
    await this.connectLive(true);
  }

  closeLive() {
    if (this.mode !== "livestream") return;
    this.liveConnection?.close();
    this.liveConnection = null;
    const video = element("live-video");
    video.srcObject = null;
    video.hidden = true;
    element("live-play").hidden = true;
    this.local?.getTracks().forEach(track => track.stop());
    this.local = null;
    element("local").srcObject = null;
    this.renderControls();
  }

  setPeerScreens(track) {
    return Promise.all([...this.peers.values()].map(({call}) => call.setScreen(this.screenStream, track)));
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

  makePeer(peer, initiates) {
    const id = peer.peer_id;
    if (this.peers.has(id)) return;
    const tile = new PeerTile(peer, kind => {
      this.emit("mute_peer", {peer_id: id, kind}).catch(error => message(error.message, true));
    });
    const call = new PeerCall({
      id,
      initiates,
      polite: this.socket.id > id,
      local: this.local,
      policy: this.policy,
      iceServers: this.iceServers,
      signal: (event, payload) => this.emit(event, {to: id, ...payload}),
      showStream: stream => tile.addStream(stream),
      showState: state => tile.setState(state),
      showError: error => message(error.message || "Kết nối video gặp lỗi.", true),
    });
    this.peers.set(id, {tile, call});
    tile.showStats(this.statsVisible);
    if (this.screen) {
      call.setScreen(this.screenStream, this.screen.getVideoTracks()[0])
        .catch(error => message(error.message, true));
    }
  }

  removePeer(id) {
    const peer = this.peers.get(id);
    if (!peer) return;
    peer.call.close();
    peer.tile.close();
    this.peers.delete(id);
  }

  resetPeers() {
    for (const id of this.peers.keys()) this.removePeer(id);
    this.pendingEvents.length = 0;
    this.renderControls();
  }

  toggleStats() {
    this.statsVisible = !this.statsVisible;
    element("stats-toggle").setAttribute("aria-pressed", String(this.statsVisible));
    for (const {tile} of this.peers.values()) tile.showStats(this.statsVisible);
    clearInterval(this.statsTimer);
    if (this.statsVisible) {
      this.statsTimer = setInterval(() => this.sampleStats(), 1000);
      this.sampleStats();
    }
  }

  async sampleStats() {
    if (this.sampling) return;
    this.sampling = true;
    try {
      await Promise.allSettled([...this.peers.values()].map(({call, tile}) => tile.sample(call.pc)));
    } finally {
      this.sampling = false;
    }
  }

  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.joined = false;
    clearTimeout(this.iceRefresh);
    clearInterval(this.statsTimer);
    this.socket.disconnect();
    this.stopScreen();
    this.closeLive();
    this.resetPeers();
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
}
element("stats-toggle").addEventListener("click", () => active?.toggleStats());
element("live-start").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await active?.toggleLive();
  } catch (error) {
    element("live-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
element("live-retry").addEventListener("click", () => {
  if (active?.joined && active.publisher && !active.liveConnection) {
    element("live-retry").hidden = true;
    active.connectLive(false);
  }
});
async function playLive() {
  const video = element("live-video");
  const stream = video.srcObject;
  try {
    await video.play();
    element("live-play").hidden = true;
  } catch {
    if (stream && video.srcObject === stream) element("live-play").hidden = false;
  }
}
element("live-play").addEventListener("click", playLive);
onForm("live-speaker-form", async ({peer_id}) => {
  if (peer_id === active.socket.id) await active.emit("demote_speaker");
  else await active.emit("promote_speaker", {peer_id});
});
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
window.addEventListener("pagehide", () => active?.stop());

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
    roomMode = room.mode;
    if (roomMode === "livestream") element("enter-room").textContent = "Vào livestream";
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
