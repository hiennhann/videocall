import { api } from "./api.js";
import { action, node } from "./room-cards.js";
import { allPages, apiWrite, auth, personRow, quickCall } from "./social-ui.js";
import { element, message } from "./ui.js";
import { loadWorkspace } from "./workspace.js";

const target = new URLSearchParams(location.search).get("user");
const uuid = /^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i;
const list = element("conversation-list");
const output = element("dm-messages");
const status = element("dm-state");
const thread = element("dm-thread");
const form = element("dm-form");
const input = form.elements.text;
const send = form.querySelector("button");
const time = new Intl.DateTimeFormat("vi-VN", {hour: "2-digit", minute: "2-digit"});
const day = new Intl.DateTimeFormat("vi-VN", {dateStyle: "full"});
const messages = new Map();
let conversations = [];
let current;
let receivedConversationId;
let state;
let older;
let pending;
let typingTimer;
let lastTyping = -Infinity;
let marked = 0;
let recovering = false;
let loadingThread = false;

function renderList() {
  const keyword = element("conversation-search").value.trim().toLocaleLowerCase("vi");
  const rows = conversations.filter(item => item.user?.display_name.toLocaleLowerCase("vi").includes(keyword));
  element("conversation-state").textContent = rows.length ? "" : keyword ?
    "Không tìm thấy cuộc trò chuyện." : "Chọn một người trong Bạn bè để bắt đầu nhắn tin.";
  list.replaceChildren(...rows.map(item => {
    const link = node("a", "Mở chat", "button button--secondary");
    link.href = "/messages?" + new URLSearchParams({user: item.user.id});
    if (item.user.id === target) link.setAttribute("aria-current", "page");
    const preview = item.last_message?.deleted_at ? "Tin nhắn đã bị xóa" : item.last_message?.text || "";
    return personRow(item.user, [preview, item.unread_count ? `${item.unread_count} chưa đọc` : ""].filter(Boolean).join(" · "), [link]);
  }));
}

async function loadList() {
  const retry = element("conversation-retry");
  retry.hidden = true;
  try {
    conversations = await allPages("/conversations");
    renderList();
  } catch (error) {
    element("conversation-state").textContent = error.message;
    retry.hidden = false;
  }
}

function merge(items) {
  for (const item of items) {
    if (!messages.get(item.id)?.deleted_at || item.deleted_at) messages.set(item.id, item);
  }
}

function renderMessages(follow = false) {
  const rows = [...messages.values()].sort((a, b) => a.id - b.id);
  const height = output.scrollHeight;
  const stick = follow || height - output.clientHeight - output.scrollTop < 72;
  const fragment = document.createDocumentFragment();
  let lastDay;
  for (const item of rows) {
    const timestamp = new Date(item.created_at);
    const label = day.format(timestamp);
    if (lastDay !== label) { fragment.append(node("li", label, "dm-day")); lastDay = label; }
    const own = item.sender_id === state.profile.id;
    const bubble = node("li", null, own ? "dm-bubble own" : "dm-bubble");
    const t = node("time", time.format(timestamp));
    t.dateTime = item.created_at;
    bubble.append(node("p", item.deleted_at ? "Tin nhắn đã bị xóa" : item.text), t);
    if (own && !item.deleted_at) {
      bubble.append(node("span", current.peer_last_read_id >= item.id ? "Đã xem" : "Đã gửi", "text-small"));
      const remove = action("Xóa", async () => {
        if (!window.confirm("Xóa tin nhắn này?")) return;
        await apiWrite(`/conversations/${current.id}/messages/${item.id}`, "DELETE");
        merge([{...item, text: null, deleted_at: new Date().toISOString()}]);
        renderMessages();
      });
      remove.setAttribute("aria-label", "Xóa tin nhắn đã gửi lúc " + t.textContent);
      bubble.append(remove);
      bubble.addEventListener("contextmenu", event => { event.preventDefault(); remove.focus(); });
    }
    fragment.append(bubble);
  }
  output.replaceChildren(fragment);
  if (stick) output.scrollTop = output.scrollHeight;
  element("dm-older").hidden = older == null;
  markRead();
}

async function markRead() {
  if (!current?.id || document.visibilityState !== "visible") return;
  const latest = Math.max(0, ...[...messages.values()].filter(item => item.sender_id !== state.profile.id).map(item => item.id));
  if (latest <= marked) return;
  const previous = marked;
  marked = latest;
  try { await apiWrite(`/conversations/${current.id}/read`, "POST", {up_to_id: latest}); }
  catch { if (marked === latest) marked = previous; }
}

function applyConversation(value) {
  current = {
    ...value,
    id: value.id ?? current?.id ?? receivedConversationId,
    peer_last_read_id: Math.max(value.peer_last_read_id, current?.peer_last_read_id ?? 0),
  };
  element("dm-title").textContent = value.user?.display_name || "Cuộc trò chuyện";
  form.hidden = !value.can_send;
  element("dm-call").hidden = !value.can_send || state.config?.meeting_enabled === false;
  status.textContent = !value.can_send ? "Bạn không thể nhắn tin cho người này. Lịch sử vẫn xem được." :
    !state.socket?.connected ? "Đang kết nối lại…" : "";
  send.disabled = !state.socket?.connected;
}

async function canSendNow() {
  if (!current) return;
  try {
    applyConversation(await api(`/conversations/with/${target}`, auth));
  } catch (error) { status.textContent = error.message; form.hidden = true; }
}

async function catchUp() {
  if (!current?.id || recovering || loadingThread) return;
  recovering = true;
  try {
    // Làm mới cửa sổ cuối để nhận cả tin đã xóa khi mất kết nối.
    let after = Math.max(0, ...messages.keys());
    const latest = await api(`/conversations/${current.id}/messages?limit=50`, auth);
    merge(latest.items);
    if (!after || messages.size <= 50) older = latest.next_before;
    while (after) {
      const data = await api(`/conversations/${current.id}/messages?after=${after}&limit=100`, auth);
      merge(data.items);
      after = data.next_after;
    }
    renderMessages();
  } catch (error) { status.textContent = error.message; }
  finally { recovering = false; }
}

async function loadThread() {
  if (!uuid.test(target ?? "")) return;
  thread.hidden = false;
  element("messages-content").classList.add("thread-open");
  status.textContent = "Đang tải tin nhắn…";
  loadingThread = true;
  try {
    const value = await api(`/conversations/with/${target}`, auth);
    applyConversation(value);
    if (current.id) {
      const batch = await api(`/conversations/${current.id}/messages`, auth);
      older = batch.next_before;
      merge(batch.items);
    }
    renderMessages(true);
  } catch (error) { status.textContent = error.message; }
  finally { loadingThread = false; }
}

async function sendMessage(event) {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || !state.socket.connected || !current?.can_send) return;
  if (!pending || pending.text !== text) pending = {to_user_id: target, text, client_msg_id: crypto.randomUUID()};
  send.disabled = true;
  try {
    const ack = await state.socket.timeout(5500).emitWithAck("dm_send", pending);
    if (!ack.ok) {
      if (["NOT_FRIENDS", "DM_DISABLED"].includes(ack.error.code)) await canSendNow();
      throw new Error(ack.error.message);
    }
    current.id = ack.data.conversation_id;
    merge([ack.data.message]);
    if (input.value.trim() === text) input.value = "";
    pending = null;
    status.textContent = "";
    renderMessages(true);
    input.focus();
    loadList();
  } catch (error) { status.textContent = error.message || "Không gửi được. Bạn có thể thử lại."; }
  finally { send.disabled = !state.socket.connected; }
}

state = await loadWorkspace();
if (state?.profile.is_guest) message("Đăng nhập tài khoản để dùng Tin nhắn.");
else if (state?.socket) {
  element("messages-content").hidden = false;
  element("conversation-state").textContent = "Đang tải cuộc trò chuyện…";
  element("conversation-search").addEventListener("input", renderList);
  element("conversation-retry").addEventListener("click", loadList);
  element("dm-call").addEventListener("click", () => quickCall(target).catch(error => message(error.message, true)));
  form.addEventListener("submit", sendMessage);
  input.addEventListener("input", () => {
    if (state.socket.connected && input.value.trim() && performance.now() - lastTyping > 2100) {
      lastTyping = performance.now();
      state.socket.emit("dm_typing", {to_user_id: target, typing: true});
    }
  });
  element("dm-older").addEventListener("click", async event => {
    const button = event.currentTarget;
    button.disabled = true;
    const height = output.scrollHeight;
    const before = output.scrollTop;
    try {
      const batch = await api(`/conversations/${current.id}/messages?before=${older}`, auth);
      older = batch.next_before;
      merge(batch.items);
      renderMessages();
      output.scrollTop = before + output.scrollHeight - height;
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
  window.addEventListener("videocall:communications-synced", ({detail}) => {
    conversations = detail.conversations;
    renderList();
    const match = detail.conversations.find(item => item.user?.id === target);
    if (!current || !match) return;
    applyConversation(match);
    const recovered = detail.recovered.filter(item => item.conversation_id === current.id).map(item => item.message);
    if (recovered.length) { merge(recovered); renderMessages(); }
  });
  state.socket.on("dm_message", event => {
    if (event.conversation_id !== current?.id && event.message.sender_id !== target) return;
    merge([event.message]);
    if (!current) {
      receivedConversationId = event.conversation_id;
      return;
    }
    current.id = event.conversation_id;
    renderMessages();
  });
  state.socket.on("dm_read", ({conversation_id, by_user_id, up_to_id}) => {
    if (current?.id !== conversation_id || by_user_id !== target) return;
    current.peer_last_read_id = Math.max(current.peer_last_read_id, up_to_id);
    renderMessages();
  });
  state.socket.on("dm_typing", ({from_user_id, typing}) => {
    if (from_user_id !== target) return;
    const indicator = element("dm-typing-state");
    indicator.textContent = typing ? "Đang nhập…" : "";
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => { indicator.textContent = ""; }, 3000);
  });
  state.socket.on("friend_removed", ({user_id}) => { if (user_id === target) canSendNow(); });
  state.socket.on("friend_added", ({user}) => { if (user.id === target) canSendNow(); });
  state.socket.on("connect", async () => { await canSendNow(); await catchUp(); });
  state.socket.on("disconnect", () => { status.textContent = "Đang kết nối lại…"; send.disabled = true; });
  document.addEventListener("visibilitychange", markRead);
  await Promise.all([loadList(), loadThread()]);
}
