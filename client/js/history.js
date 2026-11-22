import { api } from "./api.js";
import { initDialogs } from "./app/components/primitives.js";
import { action, node } from "./room-cards.js";
import { apiWrite, auth, dateTime, downloadChat, personAvatar } from "./social-ui.js";
import { element, message, onForm } from "./ui.js";
import { loadWorkspace } from "./workspace.js";

const form = element("history-filter");
const detail = element("history-detail");
const filters = ["hosted", "joined", "missed_invite"];
const labels = {hosted: "Đã chủ trì", joined: "Đã tham gia", missed_invite: "Lỡ lời mời"};
const reasons = {left: "Tự rời", disconnected: "Mất kết nối", kicked: "Bị mời ra",
  room_closed: "Phòng đã đóng", session_replaced: "Chuyển phiên", server_restart: "Máy chủ khởi động lại"};
let page = 1;
let requestId = 0;
let detailId = 0;
let selected;
const stamp = value => value ? dateTime.format(new Date(value)) : "—";
const duration = value => value >= 60 ? `${Math.floor(value / 60)} phút ${value % 60} giây` : `${value || 0} giây`;

async function load() {
  const current = ++requestId;
  const status = element("history-state");
  const list = element("history-list");
  const retry = element("history-retry");
  const params = new URLSearchParams({page: String(page), page_size: "15"});
  const values = form.elements;
  retry.hidden = true;
  status.textContent = "Đang tải lịch sử…";
  list.setAttribute("aria-busy", "true");
  try {
    if (values.type.value) params.set("type", values.type.value);
    if (values.from.value) params.set("from", new Date(values.from.value + "T00:00:00").toISOString());
    if (values.to.value) params.set("to", new Date(values.to.value + "T23:59:59.999").toISOString());
    if (values.from.value && values.to.value && values.from.value > values.to.value) {
      throw new Error("Ngày kết thúc phải từ ngày bắt đầu trở đi.");
    }
    const data = await api("/me/call-history?" + params, auth);
    if (current !== requestId) return;
    list.replaceChildren(...data.items.map(call => {
      const row = node("li", null, "panel history-row");
      const info = node("div");
      info.append(node("strong", call.name || call.room_code),
        node("p", `${labels[call.type]} · ${stamp(call.started_at)} · ${duration(call.duration_seconds)} · ${call.participants_count} người`, "muted text-small"));
      const avatars = node("div", null, "history-avatars");
      avatars.append(...call.participants_preview.map(user => personAvatar(user, 28)));
      row.append(info, avatars, action("Chi tiết", () => showDetail(call)));
      return row;
    }));
    status.textContent = data.total ? `${data.total} mục lịch sử` : "Không có cuộc gọi phù hợp.";
    element("history-page").textContent = `Trang ${page} / ${Math.max(1, Math.ceil(data.total / data.page_size))}`;
    element("history-prev").disabled = page <= 1;
    element("history-next").disabled = page * data.page_size >= data.total;
  } catch (error) {
    if (current !== requestId) return;
    status.textContent = error.message;
    retry.hidden = false;
  } finally {
    if (current === requestId) list.removeAttribute("aria-busy");
  }
}

async function showDetail(call) {
  const current = ++detailId;
  const people = element("history-people");
  const status = element("history-detail-state");
  selected = null;
  people.replaceChildren();
  element("export-history-chat").disabled = true;
  element("chat-expiry").hidden = true;
  element("history-title").textContent = call.name || call.room_code;
  status.textContent = "Đang tải chi tiết…";
  detail.showModal();
  try {
    const data = await api(`/me/call-history/${call.room_code}`, auth);
    if (current !== detailId || !detail.open) return;
    selected = data;
    status.textContent = `Mã ${data.room_code} · Bắt đầu ${stamp(data.started_at)} · Kết thúc ${stamp(data.ended_at)}`;
    people.replaceChildren(...data.participants.map(person => {
      const row = node("li", null, "panel");
      row.append(node("strong", person.display_name), node("p",
        `Vào ${stamp(person.joined_at)} · Rời ${stamp(person.left_at)}${reasons[person.leave_reason] ? " · " + reasons[person.leave_reason] : ""}`, "muted text-small"));
      return row;
    }));
    if (!people.childElementCount) people.append(node("li", "Không có thông tin người tham gia."));
    element("export-history-chat").disabled = !data.chat_available;
    element("chat-expiry").hidden = data.chat_available;
  } catch (error) { if (current === detailId) status.textContent = error.message; }
}

const state = await loadWorkspace();
if (state?.profile.is_guest) message("Đăng nhập tài khoản để xem lịch sử cuộc gọi.");
else if (state && state.config?.call_history_enabled === false) message("Lịch sử cuộc gọi đang tắt.");
else if (state) {
  initDialogs();
  element("history-content").hidden = false;
  const initial = new URLSearchParams(location.search).get("type");
  if (filters.includes(initial)) form.elements.type.value = initial;
  form.addEventListener("submit", event => { event.preventDefault(); page = 1; load(); });
  element("history-prev").addEventListener("click", () => { page--; load(); });
  element("history-next").addEventListener("click", () => { page++; load(); });
  element("history-retry").addEventListener("click", load);
  element("export-history-chat").addEventListener("click", async () => {
    if (!selected?.chat_available) return;
    try { await downloadChat(selected.room_code); }
    catch (error) { element("history-detail-state").textContent = error.message; }
  });
  const clear = element("clear-history-dialog");
  element("clear-history").addEventListener("click", () => {
    element("clear-history-form").reset();
    clear.showModal();
  });
  onForm("clear-history-form", async () => {
    try {
      await apiWrite("/me/call-history", "DELETE");
      clear.close();
      page = 1;
      await load();
      message("Đã xóa lịch sử khỏi tài khoản của bạn.");
    } catch (error) { clear.close(); throw error; }
  });
  await load();
}
