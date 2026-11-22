import { api } from "./api.js";
import { icon } from "./app/components/primitives.js";
import { action, node } from "./room-cards.js";
import { apiWrite, auth } from "./social-ui.js";
import { openInvite } from "./ui.js";

export const inviteSoundKey = "videocall.invite-sound";

export function bindNotifications(socket, config) {
  const header = document.querySelector(".header-actions");
  const details = node("details", null, "notification-menu");
  const summary = node("summary", null, "secondary");
  const count = node("span", "0", "badge badge--primary");
  summary.append(icon("bell"), count);
  const list = node("ul", null, "notification-list panel");
  details.append(summary, list);
  header.prepend(details);
  const card = node("section", null, "panel incoming-call");
  card.hidden = true;
  const alert = node("p");
  alert.setAttribute("role", "alert");
  const countdown = node("p", null, "muted text-small");
  const controls = node("div", null, "controls");
  card.append(alert, countdown, controls);
  document.body.append(card);

  const invites = new Map();
  let requests = [];
  let missed = [];
  let featured;
  let missedRevision = 0;
  let sound;
  const heard = new Set();
  function armSound() {
    if (localStorage.getItem(inviteSoundKey) !== "true") return;
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    sound ??= new Audio();
    sound.resume().catch(() => {});
  }
  document.addEventListener("pointerdown", armSound);
  document.addEventListener("keydown", armSound);
  function ring(id) {
    if (heard.has(id)) return;
    heard.add(id);
    if (sound?.state !== "running" || localStorage.getItem(inviteSoundKey) !== "true") return;
    const oscillator = sound.createOscillator();
    const gain = sound.createGain();
    gain.gain.value = 0.045;
    oscillator.frequency.value = 660;
    oscillator.connect(gain).connect(sound.destination);
    oscillator.start();
    oscillator.stop(sound.currentTime + 0.18);
  }
  async function refreshMissed() {
    if (config?.call_history_enabled === false) return;
    const version = ++missedRevision;
    try {
      const data = await api("/me/call-history?type=missed_invite&page_size=5", auth);
      if (version === missedRevision) { missed = data.items; renderMenu(); }
    } catch { /* The inbox remains usable if history cannot be read. */ }
  }
  function inviteActions(invite) {
    return [
      action("Từ chối", async () => {
        try { await apiWrite(`/invites/${invite.id}/decline`, "POST"); }
        catch (error) { if (error.status !== 410 && error.status !== 404) throw error; }
        remove(invite.id);
      }),
      action("Tham gia", () => openInvite(invite), ""),
    ];
  }
  function renderMenu() {
    count.textContent = String(invites.size + requests.length);
    summary.setAttribute("aria-label", `Thông báo, ${count.textContent} mục đang chờ`);
    const rows = [...invites.values()].map(invite => {
      const row = node("li");
      row.append(node("p", `${invite.from?.display_name || "Bạn bè"} mời vào ${invite.room.name || invite.room.code}`));
      const actions = node("div", null, "controls");
      actions.append(...inviteActions(invite));
      row.append(actions);
      return row;
    });
    for (const [items, path, prefix, label] of [
      [requests, "/friends?tab=requests", "Lời mời kết bạn từ", item => item.from.display_name],
      [missed, "/history?type=missed_invite", "Lỡ lời mời", item => item.name || item.room_code],
    ]) {
      for (const item of items) {
        const row = node("li");
        const link = node("a", `${prefix} ${label(item)}`);
        link.href = path;
        row.append(link);
        rows.push(row);
      }
    }
    list.replaceChildren(...(rows.length ? rows : [node("li", "Chưa có thông báo.")]));
  }
  function showFeatured() {
    if (featured && invites.has(featured)) return;
    const invite = invites.values().next().value;
    featured = invite?.id;
    card.hidden = !invite;
    if (!invite) return;
    alert.textContent = `${invite.from?.display_name || "Bạn bè"} mời bạn vào “${invite.room.name || invite.room.code}”.`;
    controls.replaceChildren(...inviteActions(invite));
    ring(invite.id);
  }
  function remove(id) {
    if (!invites.delete(id)) return;
    renderMenu();
    showFeatured();
  }
  function tick() {
    let expired = false;
    for (const invite of invites.values()) {
      if (Date.parse(invite.expires_at) <= Date.now()) { remove(invite.id); expired = true; }
    }
    if (expired) refreshMissed();
    if (!featured) return;
    const invite = invites.get(featured);
    const rest = Math.max(0, Math.ceil((Date.parse(invite.expires_at) - Date.now()) / 1000));
    countdown.textContent = `${invite.room.has_password ? "Phòng riêng · " : ""}Hết hạn sau ${Math.floor(rest / 60)}:${String(rest % 60).padStart(2, "0")}`;
  }
  function invited({invite}) {
    invites.set(invite.id, invite);
    renderMenu();
    showFeatured();
    tick();
  }
  function cancelled({invite_id, reason}) {
    remove(invite_id);
    if (reason === "expired") refreshMissed();
  }
  function friendSnapshot({detail}) {
    requests = detail.incoming;
    renderMenu();
  }
  function communicationSnapshot({detail}) {
    invites.clear();
    for (const invite of detail.invites) invites.set(invite.id, invite);
    renderMenu();
    showFeatured();
    tick();
  }
  function handleEscape(event) {
    if (event.key === "Escape" && details.open) { details.open = false; summary.focus(); }
  }
  details.addEventListener("keydown", handleEscape);
  socket.on("call_invite", invited);
  socket.on("call_invite_cancelled", cancelled);
  window.addEventListener("videocall:friends-synced", friendSnapshot);
  window.addEventListener("videocall:communications-synced", communicationSnapshot);
  const timer = setInterval(tick, 1000);
  renderMenu();
  refreshMissed();
  return () => {
    clearInterval(timer);
    missedRevision++;
    socket.off("call_invite", invited);
    socket.off("call_invite_cancelled", cancelled);
    window.removeEventListener("videocall:friends-synced", friendSnapshot);
    window.removeEventListener("videocall:communications-synced", communicationSnapshot);
    document.removeEventListener("pointerdown", armSound);
    document.removeEventListener("keydown", armSound);
    sound?.close().catch(() => {});
    details.remove();
    card.remove();
  };
}
