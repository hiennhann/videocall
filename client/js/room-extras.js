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
  let loading = false;
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
      options.replaceChildren(...list.map(friend => {
        const label = node("label", null, "invite-option");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.name = "friend";
        checkbox.value = friend.id;
        label.append(checkbox, node("span", friend.display_name));
        return label;
      }));
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
      const names = new Map([...form.elements].filter(input => input.name === "friend")
        .map(input => [input.value, input.parentElement.textContent]));
      const skipped = result.skipped.map(item => `${names.get(item.user_id)}: ${reasons[item.reason]}`);
      status.textContent = [`Đã gửi ${result.sent.length} lời mời.`, ...skipped].join(" ");
      form.reset();
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
