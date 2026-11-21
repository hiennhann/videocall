import { element } from "./ui.js";

export const mediaButtons = {audio: ["mic", "Mic"], video: ["camera", "Camera"]};
const capture = {width: {ideal: 1280}, height: {ideal: 720}};

export function mediaError(error) {
  return {
    NotAllowedError: "Hãy cho phép trang dùng camera và mic, rồi thử lại.",
    NotFoundError: "Không tìm thấy camera hoặc mic. Kiểm tra thiết bị rồi thử lại.",
    NotReadableError: "Camera hoặc mic đang bận. Hãy đóng ứng dụng đang sử dụng thiết bị.",
    OverconstrainedError: "Thiết bị đã chọn không còn sẵn sàng. Hãy chọn thiết bị mặc định.",
  }[error.name] || error.message || "Không thể mở camera và mic.";
}

export function setButton(button, label, enabled) {
  button.setAttribute("aria-pressed", String(enabled));
  button.textContent = `${label} ${enabled ? "bật" : "tắt"}`;
}

export class Precall {
  constructor() {
    this.video = element("preview");
    this.audioDevice = element("audio-device");
    this.videoDevice = element("video-device");
    this.speaker = element("speaker-device");
    this.enabled = {audio: true, video: true};
    this.startButton = element("preview-start");
    this.startButton.addEventListener("click", () => this.preview());
    for (const kind of ["audio", "video"]) {
      const [id, label] = mediaButtons[kind];
      const button = element(`preview-${id}`);
      button.addEventListener("click", () => {
        this.enabled[kind] = !this.enabled[kind];
        setButton(button, label, this.enabled[kind]);
        this.applyTracks();
      });
    }
    for (const device of [this.audioDevice, this.videoDevice]) {
      device.addEventListener("change", () => this.preview());
    }
    window.addEventListener("pagehide", () => this.stop());
  }

  async getMedia() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Camera và mic cần localhost hoặc HTTPS trên trình duyệt hỗ trợ WebRTC.");
    }
    const device = select => select.value ? {deviceId: {exact: select.value}} : {};
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: device(this.audioDevice), video: {...capture, ...device(this.videoDevice)},
    });
    for (const track of stream.getTracks()) track.enabled = this.enabled[track.kind];
    return stream;
  }

  async preview() {
    if (this.pending) return;
    this.stop();
    const revision = this.revision;
    const error = element("preview-error");
    error.hidden = true;
    this.startButton.disabled = element("enter-room").disabled = true;
    this.pending = true;
    try {
      const stream = await this.getMedia();
      if (revision !== this.revision) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      this.stream = stream;
      this.video.srcObject = stream;
      this.applyTracks();
      element("preview-mic").hidden = element("preview-camera").hidden = false;
      this.startButton.textContent = "Kiểm tra lại thiết bị";
      await this.showDevices();
      if (revision === this.revision) this.monitorMic(stream);
    } catch (err) {
      error.textContent = mediaError(err);
      error.hidden = false;
    } finally {
      this.pending = false;
      this.startButton.disabled = element("enter-room").disabled = false;
    }
  }

  async showDevices() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    for (const [kind, select, label] of [
      ["videoinput", this.videoDevice, "Camera"],
      ["audioinput", this.audioDevice, "Mic"],
      ["audiooutput", this.speaker, "Loa"],
    ]) {
      const previous = select.value;
      select.replaceChildren(new Option("Mặc định", ""), ...devices.filter(device => device.kind === kind && device.deviceId)
        .map((device, index) => new Option(device.label || `${label} ${index + 1}`, device.deviceId)));
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
    }
    element("speaker-device-label").hidden = typeof this.video.setSinkId !== "function" || this.speaker.length < 2;
    element("media-devices").hidden = false;
  }

  applyTracks() {
    for (const track of this.stream?.getTracks() ?? []) track.enabled = this.enabled[track.kind];
    this.video.hidden = !this.stream || !this.enabled.video;
    element("preview-placeholder").toggleAttribute("hidden", !this.video.hidden);
  }

  monitorMic(stream) {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio || !stream.getAudioTracks().length) return;
    const audio = this.audio = new Audio();
    const analyser = audio.createAnalyser();
    analyser.fftSize = 256;
    audio.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    element("preview-level").hidden = false;
    audio.resume().catch(() => {});
    this.timer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
      element("preview-meter").value = this.enabled.audio ? Math.min(1, rms * 4) : 0;
    }, 100);
  }

  detach() {
    this.revision = (this.revision || 0) + 1;
    clearInterval(this.timer);
    this.audio?.close().catch(() => {});
    this.audio = null;
    const stream = this.stream;
    this.stream = null;
    this.video.srcObject = null;
    this.applyTracks();
    element("preview-level").hidden = true;
    element("preview-meter").value = 0;
    return stream;
  }

  async forCall() { return this.detach() ?? await this.getMedia(); }

  stop() { this.detach()?.getTracks().forEach(track => track.stop()); }
}
