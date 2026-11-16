export class LiveConnection {
  constructor(iceServers, stream, onStream, onState) {
    this.pc = new RTCPeerConnection({iceServers, bundlePolicy: "max-bundle"});
    const remote = new MediaStream();
    this.pc.ontrack = ({track}) => {
      remote.addTrack(track);
      onStream(remote);
    };
    this.pc.onconnectionstatechange = () => onState(this.pc.connectionState);
    for (const kind of ["audio", "video"]) {
      const track = stream?.getTracks().find(track => track.kind === kind);
      const options = track ? {direction: "sendonly", streams: [stream]} : {direction: "recvonly"};
      const transceiver = this.pc.addTransceiver(track ?? kind, options);
      if (kind === "video" && RTCRtpSender.getCapabilities && transceiver.setCodecPreferences) {
        const vp8 = RTCRtpSender.getCapabilities(kind)?.codecs.filter(codec => codec.mimeType === "video/VP8");
        if (vp8?.length) transceiver.setCodecPreferences(vp8);
      }
    }
  }

  async connect(answer) {
    const pc = this.pc;
    await pc.setLocalDescription(await pc.createOffer());
    if (pc.iceGatheringState !== "complete") {
      await new Promise(resolve => {
        const done = () => {
          clearTimeout(timer);
          pc.removeEventListener("icegatheringstatechange", check);
          this.finishGathering = null;
          resolve();
        };
        const check = () => { if (pc.iceGatheringState === "complete") done(); };
        const timer = setTimeout(done, 4000);
        this.finishGathering = done;
        pc.addEventListener("icegatheringstatechange", check);
      });
    }
    if (pc.signalingState === "closed") return;
    const result = await answer(pc.localDescription.toJSON());
    if (pc.signalingState !== "closed") await pc.setRemoteDescription(result);
  }

  close() {
    this.finishGathering?.();
    this.pc.ontrack = null;
    this.pc.onconnectionstatechange = null;
    this.pc.close();
  }
}
