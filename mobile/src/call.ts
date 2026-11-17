import {mediaDevices, registerGlobals, type MediaStream} from "react-native-webrtc";
import type {Socket} from "socket.io-client";

import {LiveConnection} from "../../client/js/live.js";
import {PeerCall} from "../../client/js/webrtc.js";
import {api} from "./api";

registerGlobals();

export interface Room {
  code: string;
  name: string | null;
  mode: "meeting" | "livestream";
  status: "active" | "closed";
  has_password: boolean;
}

interface Peer {
  peer_id: string;
  display_name: string;
}

interface Snapshot {
  room: {publisher_peer_id: string | null};
  peers: Peer[];
  media_policy: {max_video_bitrate_kbps: number};
}

interface IceCredentials {
  urls: string[];
  username?: string;
  credential?: string;
}

export interface RemoteVideo {
  id: string;
  name: string;
  stream: MediaStream;
}

interface View {
  local: (stream: MediaStream | null) => void;
  remotes: (streams: RemoteVideo[]) => void;
  status: (text: string) => void;
  closed: (text: string) => void;
}

export class RoomCall {
  private local: MediaStream | null = null;
  private peers = new Map<string, PeerCall>();
  private streams = new Map<string, RemoteVideo>();
  private disposers: (() => void)[] = [];
  private pending: (() => void)[] = [];
  private live: LiveConnection | null = null;
  private publisher: string | null = null;
  private iceServers: IceCredentials[] = [];
  private policy: Snapshot["media_policy"] = {max_video_bitrate_kbps: 0};
  private disposed = false;
  private joined = false;

  constructor(
    private socket: Socket,
    private room: Room,
    private password: string,
    private view: View,
  ) {}

  async start() {
    const ice = await api<IceCredentials>("/turn-credentials", {authenticated: true});
    this.iceServers = ice.urls.length ? [ice] : [];
    if (this.disposed) return;
    if (this.room.mode === "meeting") {
      const stream = await mediaDevices.getUserMedia({audio: true, video: {facingMode: "user"}});
      if (this.disposed) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      this.local = stream;
      this.view.local(stream);
    }
    this.listen("connect", () => { this.join().catch(error => this.fail(error)); });
    this.listen("disconnect", () => {
      this.resetPeers();
      this.view.status("Đang kết nối lại phòng…");
    });
    this.listen("room_closed", () => this.view.closed("Phòng đã đóng."));
    this.listen("kicked", () => this.view.closed("Bạn đã rời phòng theo yêu cầu của host."));
    this.listen("peer_joined", ({peer}: {peer: Peer}) => {
      this.afterJoin(() => this.addPeer(peer, false));
    });
    this.listen("peer_left", ({peer_id}: {peer_id: string}) => {
      this.afterJoin(() => this.removePeer(peer_id));
    });
    for (const event of ["offer", "answer", "ice_candidate"]) {
      this.listen(event, ({from, sdp, candidate}: {from: string; sdp?: unknown; candidate?: unknown}) => {
        this.afterJoin(() => {
          const peer = this.peers.get(from);
          if (event === "ice_candidate") void peer?.receiveCandidate(candidate);
          else void peer?.receiveDescription(sdp);
        });
      });
    }
    this.listen("track_published", ({peer_id}: {peer_id: string}) => {
      this.afterJoin(() => this.watch(peer_id));
    });
    this.listen("track_unpublished", () => this.afterJoin(() => this.watch(null)));
    this.listen("force_mute", ({kind}: {kind: "audio" | "video"}) => {
      this.toggle(kind, false);
      this.view.status(kind === "audio" ? "Host đã tắt mic của bạn." : "Host đã tắt camera của bạn.");
    });
    if (this.socket.connected) await this.join();
  }

  private listen(event: string, handler: (...args: any[]) => void) {
    this.socket.on(event, handler);
    this.disposers.push(() => this.socket.off(event, handler));
  }

  private afterJoin(work: () => void) {
    if (this.joined) work();
    else if (this.pending.length < 300) this.pending.push(work);
  }

  private async send<T>(event: string, data?: unknown): Promise<T> {
    if (!this.socket.connected) throw new Error("Kết nối phòng đang gián đoạn.");
    const reply = await this.socket.timeout(10000).emitWithAck(event, data);
    if (!reply?.ok) throw new Error(reply?.error?.message || "Không thể thực hiện thao tác trong phòng.");
    return reply.data as T;
  }

  private async join() {
    const sid = this.socket.id;
    this.view.status("Đang vào phòng…");
    const ready = await this.send<Snapshot>("join_room", {
      code: this.room.code, password: this.password || null,
    });
    if (this.disposed || this.socket.id !== sid) return;
    this.joined = true;
    this.policy = ready.media_policy;
    this.view.status("Đã vào phòng.");
    if (this.room.mode === "meeting") {
      for (const peer of ready.peers) this.addPeer(peer, true);
    } else {
      this.watch(ready.room.publisher_peer_id);
    }
    this.pending.splice(0).forEach(event => event());
  }

  private addPeer(peer: Peer, initiates: boolean) {
    if (!this.local || this.peers.has(peer.peer_id)) return;
    const id = peer.peer_id;
    this.peers.set(id, new PeerCall({
      id, initiates, polite: (this.socket.id || "") > id,
      local: this.local, policy: this.policy, iceServers: this.iceServers,
      signal: (event: string, data: object) => this.send(event, {to: id, ...data}),
      showStream: (stream: MediaStream) => this.showStream(id, peer.display_name, stream),
      showState: (state: string) => {
        if (state === "failed") this.view.status("Kết nối video với " + peer.display_name + " bị gián đoạn.");
      },
      showError: (error: unknown) => this.fail(error),
    }));
  }

  private showStream(id: string, name: string, stream: MediaStream) {
    if (this.disposed) return;
    this.streams.set(id, {id, name, stream});
    this.view.remotes([...this.streams.values()]);
  }

  private removePeer(id: string) {
    this.peers.get(id)?.close();
    this.peers.delete(id);
    this.streams.delete(id);
    this.view.remotes([...this.streams.values()]);
  }

  private watch(id: string | null, retry = false) {
    if (this.publisher === id && this.live && !retry) return;
    this.live?.close();
    this.live = null;
    this.publisher = id;
    this.removePeer("live");
    if (!id) {
      this.view.status("Đang chờ người phát.");
      return;
    }
    this.view.status("Đang kết nối livestream…");
    const connection = new LiveConnection(
      this.iceServers, null, (stream: MediaStream) => this.showStream("live", "Livestream", stream),
      (state: string) => {
        if (state === "connected") this.view.status("Đang xem livestream.");
        if (state === "failed") this.view.status("Kết nối livestream bị gián đoạn.");
      },
    );
    this.live = connection;
    connection.connect((description: object) => this.send("subscribe", description))
      .catch((error: unknown) => { if (this.live === connection) this.fail(error); });
  }

  retryViewing() {
    if (this.joined) this.watch(this.publisher, true);
  }

  toggle(kind: "audio" | "video", enabled: boolean) {
    if (!this.local || this.disposed) return;
    for (const track of this.local.getTracks()) {
      if (track.kind === kind) track.enabled = enabled;
    }
    if (this.joined) {
      void this.send("media_state", {
        audio: this.local.getAudioTracks().some(track => track.enabled),
        video: this.local.getVideoTracks().some(track => track.enabled),
        screen: false,
      }).catch(error => this.fail(error));
    }
  }

  private resetPeers() {
    this.joined = false;
    this.pending.length = 0;
    this.live?.close();
    this.live = null;
    this.publisher = null;
    for (const peer of this.peers.values()) peer.close();
    this.peers.clear();
    this.streams.clear();
    if (!this.disposed) this.view.remotes([]);
  }

  private fail(error: unknown) {
    if (!this.disposed) {
      this.view.status(error instanceof Error ? error.message : "Kết nối phòng gặp lỗi.");
    }
  }

  close(leave = true) {
    if (this.disposed) return;
    this.disposed = true;
    if (leave && this.socket.connected && this.joined) this.socket.emit("leave_room");
    this.disposers.forEach(dispose => dispose());
    this.resetPeers();
    this.local?.getTracks().forEach(track => track.stop());
    this.local = null;
  }
}
