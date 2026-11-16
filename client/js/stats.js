function rate(report, previous, key) {
  const delta = report[key] - previous?.[key];
  const elapsedMs = report.timestamp - previous?.timestamp;
  return delta >= 0 && elapsedMs > 0 ? delta * 8 / elapsedMs : undefined;
}

const ms = value => Number.isFinite(value) ? (value * 1000).toFixed(1) + " ms" : "—";
const kbps = value => Number.isFinite(value) ? Math.round(value) + " kbps" : "—";

export function networkStats(report, previous) {
  const rows = [...report.values()];
  const transport = rows.find(row => row.type === "transport" && row.selectedCandidatePairId);
  const pair = report.get(transport?.selectedCandidatePairId)
    ?? rows.find(row => row.type === "candidate-pair" && row.nominated && row.state === "succeeded");
  if (!pair) return "Đang chờ số liệu mạng…";
  const candidates = [report.get(pair.localCandidateId), report.get(pair.remoteCandidateId)];
  const path = candidates.some(candidate => candidate?.candidateType === "relay") ? "TURN" : "P2P";
  const incoming = rows.filter(row => row.type === "inbound-rtp");
  const jitters = incoming.map(row => row.jitter).filter(Number.isFinite);
  const fps = incoming.filter(row => (row.kind ?? row.mediaType) === "video")
    .map(row => row.framesPerSecond).filter(Number.isFinite);
  let lost = 0;
  let received = 0;
  for (const row of incoming) {
    const before = previous?.get(row.id);
    const delta = row.packetsReceived - before?.packetsReceived;
    if (!(delta >= 0)) continue;
    received += delta;
    lost += Math.max(0, row.packetsLost - before.packetsLost) || 0;
  }
  const loss = received + lost > 0 ? (100 * lost / (received + lost)).toFixed(1) + "%" : "—";
  const before = previous?.get(pair.id);
  return [
    path, "RTT " + ms(pair.currentRoundTripTime), "Jitter " + ms(Math.max(...jitters)),
    "Mất gói " + loss, "Nhận " + kbps(rate(pair, before, "bytesReceived")),
    "Gửi " + kbps(rate(pair, before, "bytesSent")), "FPS " + (fps.length ? Math.max(...fps) : "—"),
  ].join(" · ");
}
