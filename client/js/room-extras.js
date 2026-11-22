import { api } from "./api.js";
import { element } from "./ui.js";
import { action, node } from "./room-cards.js";

const drawer = element("room-sidebar");
const drawerButton = element("room-drawer-toggle");
const mobile = matchMedia("(max-width: 767px)");
function setDrawer(open) {
  drawer.classList.toggle("drawer-open", open);
  drawerButton.setAttribute("aria-expanded", String(open));
  if (open) drawer.querySelector('[aria-selected="true"]').focus();
  else if (mobile.matches && drawer.contains(document.activeElement)) drawerButton.focus();
}
drawerButton.addEventListener("click", () => setDrawer(!drawer.classList.contains("drawer-open")));
element("room-drawer-close").addEventListener("click", () => setDrawer(false));
drawer.addEventListener("keydown", event => {
  if (event.key === "Escape" && mobile.matches) setDrawer(false);
});
mobile.addEventListener("change", () => setDrawer(false));

export function roomMemberRow(peer, canManage, emit) {
  const row = node("li", null, "room-member");
  row.append(node("span", peer.display_name));
  if (canManage && peer.peer_id) {
    row.append(action("Mời ra", async () => {
      if (window.confirm(`Mời “${peer.display_name}” ra khỏi phòng?`)) {
        await emit("kick", {peer_id: peer.peer_id});
      }
    }));
  }
  return row;
}

export function bindRoomInvites(code, canInvite) {
  const tab = element("invite-tab");
  const form = element("call-invite-form");
  const status = element("invite-status");
  const options = element("invite-options");
  const search = element("invite-search");
  const submit = form.querySelector("button[type=submit]");
  const sent = new Map();
  const byInvite = new Map();
  let friends = [];
  let loading = false;
  function showFriends() {
    const keyword = search.value.trim().toLocaleLowerCase("vi");
    for (const row of options.children) {
      row.hidden = !row.dataset.name.includes(keyword);
    }
    const count = new FormData(form).getAll("friend").length;
    submit.textContent = count ? `Gửi lời mời (${count})` : "Gửi lời mời";
  }
  function renderFriends() {
    const checked = new Set(new FormData(form).getAll("friend"));
    options.replaceChildren(...friends.map(friend => {
      const label = node("label", null, "invite-option");
      label.dataset.name = friend.display_name.toLocaleLowerCase("vi");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = "friend";
      checkbox.value = friend.id;
      const outcome = sent.get(friend.id);
      checkbox.disabled = outcome === "pending" || outcome === "accepted";
      checkbox.checked = !checkbox.disabled && checked.has(friend.id);
      const description = {pending: "Đã mời", accepted: "Đã tham gia", declined: "Đã từ chối"}[outcome] ??
        (friend.is_online === true ? "Trực tuyến" : friend.is_online === false ? "Ngoại tuyến" : "");
      label.append(checkbox, node("span", friend.display_name));
      if (description) label.append(node("small", description, "muted"));
      return label;
    }));
    showFriends();
  }
  search.addEventListener("input", showFriends);
  options.addEventListener("change", showFriends);
  element("invite-copy").addEventListener("click", () => element("copy-code").click());
  // The call socket dispatches these events for the invite form it owns.
  form.addEventListener("invite-result", ({detail}) => {
    const userId = byInvite.get(detail.invite_id);
    if (!userId) return;
    if (detail.status === "accepted" || detail.status === "declined") sent.set(userId, detail.status);
    else sent.delete(userId);
    renderFriends();
  });
  async function load() {
    if (!canInvite() || loading) return;
    loading = true;
    status.textContent = "Đang tải bạn bè…";
    form.hidden = true;
    try {
      const list = [];
      for (let page = 1; ; page++) {
        const data = await api(`/friends?page_size=100&page=${page}`, {authenticated: true});
        list.push(...data.items);
        if (list.length >= data.total || !data.items.length) break;
      }
      friends = list;
      renderFriends();
      status.textContent = list.length ? "" : "Bạn chưa có bạn bè để mời.";
      form.hidden = !list.length || !canInvite();
    } catch (error) {
      status.textContent = error.message;
    } finally { loading = false; }
  }
  new MutationObserver(() => {
    if (tab.getAttribute("aria-selected") === "true") load();
  }).observe(tab, {attributes: true, attributeFilter: ["aria-selected"]});
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!canInvite()) return;
    const ids = new FormData(form).getAll("friend");
    if (!ids.length || ids.length > 20) {
      status.textContent = "Hãy chọn từ 1 đến 20 người.";
      return;
    }
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const result = await api(`/rooms/${code}/invites`, {
        authenticated: true, method: "POST", body: {user_ids: ids},
      });
      const reasons = {already_in_room: "đang ở trong phòng", already_invited: "đã được mời",
        not_allowed: "không thể nhận lời mời", not_friend: "không còn là bạn", limit_reached: "phòng đã đạt giới hạn lời mời"};
      const names = new Map(friends.map(friend => [friend.id, friend.display_name]));
      for (const invite of result.sent) {
        byInvite.set(invite.invite_id, invite.user_id);
        sent.set(invite.user_id, "pending");
      }
      const skipped = result.skipped.map(item => `${names.get(item.user_id)}: ${reasons[item.reason]}`);
      status.textContent = [`Đã gửi ${result.sent.length} lời mời.`, ...skipped].join(" ");
      form.reset();
      renderFriends();
    } catch (error) {
      status.textContent = error.message;
    } finally { button.disabled = false; }
  });
  return () => {
    const allowed = canInvite();
    tab.hidden = !allowed;
    if (!allowed && tab.getAttribute("aria-selected") === "true") element("chat-tab").click();
  };
}
