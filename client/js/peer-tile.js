import { element } from "./ui.js";
import { incomingAudioLevel, networkStats, selectedPair } from "./stats.js";

export class PeerTile {
  constructor(peer, mute) {
    const fragment = element("peer-tile").content.cloneNode(true);
    [this.card, this.share] = fragment.children;
    this.card.dataset.peerId = peer.peer_id;
    this.share.dataset.peerId = peer.peer_id;
    this.card.querySelector(".peer-name").textContent = peer.display_name;
    this.share.querySelector("figcaption").textContent = "Màn hình của " + peer.display_name;
    this.video = this.card.querySelector("video");
    this.screen = this.share.querySelector("video");
    this.play = this.card.querySelector(".play-peer");
    this.status = this.card.querySelector(".peer-status");
    this.stats = this.card.querySelector(".network-stats");
    this.mute = this.card.querySelector(".peer-controls");
    this.streams = new Map();
    this.state = "new";
    this.play.addEventListener("click", () => this.playVideo());
    this.mute.addEventListener("click", event => {
      const kind = event.target.dataset.kind;
      if (kind) mute(kind);
    });
    this.updateMedia(peer.media);
    element("video-grid").append(fragment);
  }

  setState(state) {
    this.state = state;
    this.render();
  }

  updateMedia(media) {
    this.media = media;
    this.render();
  }

  addStream(stream) {
    this.streams.set(stream.id, stream);
    this.render();
  }

  render() {
    const media = this.media;
    const status = {
      new: "Đang kết nối", connecting: "Đang kết nối", disconnected: "Đang nối lại", failed: "Kết nối lỗi",
    };
    this.status.textContent = [
      status[this.state], media.audio ? "Mic bật" : "Mic tắt",
      media.video ? "Camera bật" : "Camera tắt", media.screen ? "Đang chia sẻ màn hình" : "",
    ].filter(Boolean).join(" · ");
    const camera = [...this.streams.values()].find(stream => stream.getAudioTracks().length);
    if (camera && this.video.srcObject !== camera) {
      this.video.srcObject = camera;
      this.playVideo();
    }
    const screen = this.streams.get(media.screen_stream_id) ?? null;
    this.share.hidden = !screen;
    if (this.screen.srcObject !== screen) this.screen.srcObject = screen;
  }

  async playVideo() {
    const stream = this.video.srcObject;
    try {
      await this.video.play();
      this.play.hidden = true;
    } catch {
      if (stream && stream === this.video.srcObject) this.play.hidden = false;
    }
  }

  showStats(visible) {
    this.stats.hidden = !visible;
  }

  async sample(pc) {
    const report = await pc.getStats();
    const pair = selectedPair(report);
    const text = networkStats(report, this.previous, pair);
    this.stats.textContent = text;
    this.card.classList.toggle("peer-speaking", this.media.audio && incomingAudioLevel(report, this.previous) >= 0.035);
    this.previous = report;
    return {roundTrip: pair?.currentRoundTripTime, text};
  }

  close() {
    this.video.srcObject = null;
    this.screen.srcObject = null;
    this.streams.clear();
    this.previous = null;
    this.card.remove();
    this.share.remove();
  }
}
