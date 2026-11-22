import { api } from "./api.js";
import { initTabs } from "./app/components/primitives.js";
import { action, node } from "./room-cards.js";
import { allPages, apiWrite, auth, personRow, quickCall } from "./social-ui.js";
import { element, message, onForm } from "./ui.js";
import { loadWorkspace } from "./workspace.js";

let data = {friends: [], incoming: [], outgoing: []};
let blocks = [];
let result;
let config;
let refreshing;

function requestButtons(item, incoming) {
  return incoming ? [
    action("Chấp nhận", () => mutate(`/friends/requests/${item.id}/accept`, "POST"), ""),
    action("Từ chối", () => mutate(`/friends/requests/${item.id}/decline`, "POST")),
  ] : [action("Hủy lời mời", () => mutate(`/friends/requests/${item.id}`, "DELETE"))];
}

async function mutate(path, method, body) {
  await apiWrite(path, method, body);
  await refresh();
}

function friendActions(friend) {
  const dm = node("a", "Nhắn tin", "button button--secondary");
  dm.href = "/messages?" + new URLSearchParams({user: friend.id});
  const menu = node("details", null, "friend-options");
  menu.append(node("summary", "Thao tác"), action("Hủy kết bạn", () => {
    if (window.confirm(`Hủy kết bạn với ${friend.display_name}?`)) return mutate(`/friends/${friend.id}`, "DELETE");
  }), action("Chặn", () => {
    if (window.confirm(`Chặn ${friend.display_name}? Hai bạn sẽ không gửi lời mời hoặc tin nhắn mới cho nhau.`)) {
      return mutate("/blocks", "POST", {user_id: friend.id});
    }
  }, "danger"));
  return [dm, action("Gọi", () => quickCall(friend.id), ""), menu];
}

function showList(id, entries, empty) {
  element(id).replaceChildren(...(entries.length ? entries : [node("li", empty, "panel muted")]));
}

function renderSearch() {
  const container = element("friend-search-result");
  container.replaceChildren();
  if (result === undefined) return;
  if (!result) { container.append(node("p", "Không tìm thấy người dùng phù hợp.", "panel")); return; }
  const friend = data.friends.find(user => user.id === result.id);
  const inbound = data.incoming.find(request => request.from.id === result.id);
  const outbound = data.outgoing.find(request => request.to.id === result.id);
  const controls = friend ? friendActions(friend) : inbound ? requestButtons(inbound, true) :
    outbound ? requestButtons(outbound, false) :
      [action("Kết bạn", () => mutate("/friends/requests", "POST", {to_user_id: result.id}), "")];
  const list = node("ul", null, "social-list");
  list.append(personRow(result, friend ? "Bạn bè" : inbound ? "Đã nhận lời mời" :
    outbound ? "Đã gửi lời mời" : "Chưa là bạn", controls));
  container.append(list);
}

function render() {
  element("friends-tab").textContent = `Bạn bè (${data.friends.length})`;
  element("requests-tab").textContent = `Lời mời (${data.incoming.length})`;
  element("blocks-tab").textContent = `Đã chặn (${blocks.length})`;
  showList("friends-list", data.friends.map(friend => personRow(friend,
    friend.is_online == null ? "" : friend.is_online ? "Trực tuyến" : "Ngoại tuyến", friendActions(friend))), "Chưa có bạn bè. Tìm bằng email để gửi lời mời.");
  showList("friends-incoming", data.incoming.map(item => personRow(item.from, "", requestButtons(item, true))), "Chưa có lời mời nhận được.");
  showList("friends-outgoing", data.outgoing.map(item => personRow(item.to, "", requestButtons(item, false))), "Chưa có lời mời đã gửi.");
  showList("friends-blocks", blocks.map(item => personRow(item.user, "",
    [action("Bỏ chặn", () => mutate(`/blocks/${item.user.id}`, "DELETE"))])), "Chưa chặn tài khoản nào.");
  renderSearch();
}

async function refresh() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const retry = element("friends-retry");
    retry.hidden = true;
    try {
      const [friends, incoming, outgoing, blocked] = await Promise.all([
        config?.friends_enabled === false ? [] : allPages("/friends"),
        config?.friends_enabled === false ? {items: []} : api("/friends/requests?direction=incoming", auth),
        config?.friends_enabled === false ? {items: []} : api("/friends/requests?direction=outgoing", auth),
        api("/blocks", auth),
      ]);
      data = {friends, incoming: incoming.items, outgoing: outgoing.items};
      blocks = blocked.items;
      if (result && blocks.some(item => item.user.id === result.id)) result = null;
      render();
    } catch (error) {
      message(error.message, true);
      retry.hidden = false;
    }
  })();
  try { await refreshing; } finally { refreshing = null; }
}

const state = await loadWorkspace();
if (state?.profile.is_guest) message("Đăng nhập tài khoản để dùng Bạn bè.");
else if (state) {
  config = state.config;
  initTabs();
  element("friends-content").hidden = false;
  element("friend-search").hidden = config?.friends_enabled === false || config?.friend_search_enabled === false;
  if (config?.friends_enabled === false) {
    message("Tính năng bạn bè đang tắt. Bạn vẫn có thể quản lý danh sách chặn.");
    element("blocks-tab").click();
  }
  if (new URLSearchParams(location.search).get("tab") === "requests") element("requests-tab").click();
  element("friends-retry").addEventListener("click", refresh);
  onForm("friend-search", async ({email}) => {
    result = undefined;
    renderSearch();
    const response = await api("/users/search?" + new URLSearchParams({email: email.trim()}), auth);
    result = response.items[0] ?? null;
    renderSearch();
  });
  window.addEventListener("videocall:friends-synced", ({detail}) => {
    if (refreshing) return;
    const focused = document.activeElement;
    if (focused.closest?.("#friends-content")) {
      // Cập nhật trạng thái mà không xóa nút người dùng đang thao tác.
      data = detail;
      return;
    }
    data = detail;
    render();
  });
  element("friends-content").addEventListener("focusout", event => {
    if (!event.currentTarget.contains(event.relatedTarget)) queueMicrotask(render);
  });
  showList("friends-list", [], "Đang tải danh sách…");
  await refresh();
}
