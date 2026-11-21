import { accessToken, api } from "./api.js";
import { initDialogs } from "./app/components/primitives.js";
import { action, node, roomCard } from "./room-cards.js";
import { element, message, openInvite } from "./ui.js";
import { loadWorkspace } from "./workspace.js";

let rooms = [];
let invites = [];
let unread = 0;
let communicationsReady = false;
const dateTime = new Intl.DateTimeFormat("vi-VN", {dateStyle: "short", timeStyle: "short"});
const details = element("call-history-dialog");

function invitationCard(invite) {
  const card = node("li", null, "room-card");
  const controls = node("div", null, "controls");
  const join = action("Tham gia", () => openInvite(invite), "");
  const decline = action("Từ chối", async () => {
    await api(`/invites/${invite.id}/decline`, {method: "POST", authenticated: true});
    invites = invites.filter(item => item.id !== invite.id);
    renderRooms();
  });
  controls.append(join, decline);
  card.append(node("span", "Lời mời", "status-pill"), node("h3", invite.room.name || invite.room.code),
    node("p", `Từ ${invite.from?.display_name ?? "một thành viên"}`, "muted text-small"),
    node("p", `Hết hạn lúc ${dateTime.format(new Date(invite.expires_at))}`, "muted text-small"), controls);
  return card;
}

function renderRooms() {
  const now = Date.now();
  const visibleInvites = invites.filter(invite => Date.parse(invite.expires_at) > now);
  const counts = [rooms.length && `${rooms.length} phòng đang mở`,
    visibleInvites.length && `${visibleInvites.length} lời mời gọi`, unread && `${unread} tin nhắn chưa đọc`];
  element("home-summary").textContent = counts.filter(Boolean).join(" · ");
  element("home-room-cards").replaceChildren(...visibleInvites.slice(0, 3).map(invitationCard),
    ...rooms.slice(0, 3).map(room => roomCard(room)));
  element("home-open-empty").hidden = Boolean(visibleInvites.length || rooms.length);
}

window.addEventListener("videocall:communications-synced", ({detail}) => {
  communicationsReady = true;
  invites = detail.invites;
  unread = detail.conversations.reduce((total, item) => total + item.unread_count, 0);
  renderRooms();
});

async function showCall(item) {
  element("call-history-title").textContent = item.name || item.room_code;
  element("call-history-status").textContent = "Đang tải chi tiết…";
  const attendees = element("call-history-attendees");
  attendees.replaceChildren();
  details.showModal();
  try {
    const call = await api(`/me/call-history/${item.room_code}`, {authenticated: true});
    if (!details.open) return;
    element("call-history-status").textContent = call.participants.length ? "" : "Chưa có thông tin người tham gia.";
    attendees.replaceChildren(...call.participants.map(participant => {
      const joined = dateTime.format(new Date(participant.joined_at));
      const left = participant.left_at ? dateTime.format(new Date(participant.left_at)) : "đang ở trong phòng";
      return node("li", `${participant.display_name} · ${joined} → ${left}`);
    }));
  } catch (error) {
    element("call-history-status").textContent = error.message;
  }
}

async function downloadChat(code) {
  const response = await fetch(`/api/v1/me/call-history/${code}/chat-export`, {
    headers: {Authorization: `Bearer ${await accessToken()}`}, cache: "no-store",
  });
  if (!response.ok) throw new Error("Hiện không tải được nhật ký chat cho phòng này.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `chat-${code}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderHistory(items) {
  const types = {hosted: "Chủ trì", joined: "Đã tham gia", missed_invite: "Lỡ lời mời"};
  element("home-history-items").replaceChildren(...items.map(item => {
    const row = node("li", null, "panel history-row");
    const copy = node("div");
    copy.append(node("strong", item.name || item.room_code), node("p", [
      types[item.type], item.started_at && dateTime.format(new Date(item.started_at)),
      item.participants_count && `${item.participants_count} người`,
      item.duration_seconds && `${Math.round(item.duration_seconds / 60)} phút`,
    ].filter(Boolean).join(" · "), "muted text-small"));
    const controls = node("div", null, "controls");
    controls.append(action("Chi tiết", () => showCall(item)));
    if (item.chat_available) controls.append(action("Tải nhật ký chat", () => downloadChat(item.room_code)));
    row.append(copy, controls);
    return row;
  }));
  element("home-history-empty").hidden = Boolean(items.length);
  element("home-history").hidden = false;
}

const state = await loadWorkspace();
if (state) {
  initDialogs();
  element("today").textContent = new Intl.DateTimeFormat("vi-VN", {dateStyle: "full"}).format(new Date());
  element("page-title").textContent = `Xin chào, ${state.profile.display_name}`;
  if (!state.profile.is_guest) {
    async function loadHome() {
      const results = await Promise.allSettled([
        api("/rooms/mine", {authenticated: true}),
        state.config?.call_history_enabled !== false ? api("/me/call-history?page_size=5", {authenticated: true}) : null,
        !communicationsReady ? api("/invites", {authenticated: true}) : null,
      ]);
      const [roomResult, history, pending] = results;
      if (pending.value && !communicationsReady) invites = pending.value.items;
      if (roomResult.status === "fulfilled") {
        rooms = roomResult.value;
        renderRooms();
        element("home-open").hidden = false;
      }
      if (history.value) renderHistory(history.value.items);
      const failure = results.find(item => item.status === "rejected" && item.reason.code !== "FEATURE_DISABLED");
      if (failure) message(failure.reason.message, true);
    }
    await loadHome();
    window.addEventListener("pageshow", event => { if (event.persisted) loadHome(); });
  }
}
