export class PeerCall {
  constructor({id, polite, initiates, local, signal, showStream, showState, showError, policy, iceServers}) {
    this.id = id;
    this.polite = polite;
    this.canOffer = initiates;
    this.signal = signal;
    this.showError = showError;
    this.candidates = [];
    this.pending = Promise.resolve();
    this.makingOffer = false;
    this.ignoreOffer = false;
    this.closed = false;
    this.policy = policy;

    const pc = this.pc = new RTCPeerConnection({iceServers});
    pc.ontrack = event => event.streams.forEach(showStream);
    pc.onconnectionstatechange = () => showState(pc.connectionState);
    pc.onicecandidate = event => {
      if (event.candidate && !this.closed) {
        this.signal("ice_candidate", {candidate: event.candidate.toJSON()})
          .catch(error => { if (!this.closed) showError(error); });
      }
    };
    pc.onnegotiationneeded = () => this.enqueue(async () => {
      if (!this.canOffer || pc.signalingState !== "stable") return;
      this.makingOffer = true;
      try {
        await pc.setLocalDescription(await pc.createOffer());
        await this.signal("offer", {sdp: pc.localDescription.toJSON()});
      } finally {
        this.makingOffer = false;
      }
    });
    for (const track of local.getTracks()) {
      const sender = pc.addTrack(track, local);
      if (track.kind === "video") limitBitrate(sender, policy.max_video_bitrate_kbps);
    }
  }

  async setScreen(stream, track = null) {
    if (this.closed) return;
    if (this.screenSender) {
      try {
        await this.screenSender.replaceTrack(track);
      } catch (error) {
        if (!this.closed) throw error;
      }
    } else if (track) {
      this.screenSender = this.pc.addTrack(track, stream);
    }
    if (track && !this.closed) limitBitrate(this.screenSender, this.policy.max_screen_bitrate_kbps);
  }

  updateIceServers(iceServers) {
    const pc = this.pc;
    pc.setConfiguration({...pc.getConfiguration(), iceServers});
    pc.restartIce();
  }

  enqueue(work) {
    this.pending = this.pending.then(async () => {
      if (!this.closed) await work();
    }).catch(error => { if (!this.closed) this.showError(error); });
    return this.pending;
  }

  receiveDescription(sdp) {
    return this.enqueue(async () => {
      const pc = this.pc;
      const collision = sdp.type === "offer" && (this.makingOffer || pc.signalingState !== "stable");
      this.ignoreOffer = !this.polite && collision;
      if (this.ignoreOffer) {
        this.candidates = [];
        return;
      }
      if (sdp.type === "answer" && pc.signalingState !== "have-local-offer") return;
      await pc.setRemoteDescription(sdp);
      const queued = this.candidates;
      this.candidates = [];
      for (const candidate of queued) await this.addCandidate(candidate);
      if (sdp.type === "offer") {
        await pc.setLocalDescription(await pc.createAnswer());
        await this.signal("answer", {sdp: pc.localDescription.toJSON()});
      }
      this.canOffer = true;
    });
  }

  receiveCandidate(candidate) {
    return this.enqueue(async () => {
      if (this.ignoreOffer) return;
      if (!this.pc.remoteDescription) {
        if (this.candidates.length < 200) this.candidates.push(candidate);
      } else {
        await this.addCandidate(candidate);
      }
    });
  }

  async addCandidate(candidate) {
    const fragment = candidate.usernameFragment;
    if (fragment && !this.pc.remoteDescription.sdp.includes("a=ice-ufrag:" + fragment)) return;
    await this.pc.addIceCandidate(candidate);
  }

  close() {
    this.closed = true;
    this.candidates = [];
    this.pc.ontrack = null;
    this.pc.onicecandidate = null;
    this.pc.onconnectionstatechange = null;
    this.pc.close();
  }
}

function limitBitrate(sender, kbps) {
  if (!kbps) return;
  const parameters = sender.getParameters();
  if (!parameters.encodings?.length) return;
  parameters.encodings[0].maxBitrate = kbps * 1000;
  sender.setParameters(parameters).catch(() => {});
}
