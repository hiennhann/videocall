import { accessToken, api, logout, requireSession, sessionEnded } from "./api.js";
import { element, message, onForm, roomUrl } from "./ui.js";
import { applyBranding } from "./theme.js";

const authenticated = true;
let presence;
const tabs = [element("join-tab"), element("create-tab")];

function selectTab(tab, focus = false) {
  for (const button of tabs) {
    const selected = button === tab;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    element(button.getAttribute("aria-controls")).hidden = !selected;
  }
  if (focus) tab.focus();
}

for (const tab of tabs) {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key) || tabs.some(button => button.hidden)) return;
    event.preventDefault();
    selectTab(tabs.find(button => button !== tab), true);
  });
}

onForm("join-form", async fields => {
  const code = fields.code.trim().toLowerCase();
  if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(code)) throw new Error("Mã phòng không đúng định dạng.");
  const room = await api("/rooms/" + code, { authenticated });
  if (room.status === "closed") throw new Error("Phòng đã đóng.");
  location.assign(roomUrl(code));
});

onForm("create-form", async fields => {
  const password = fields.password || null;
  const room = await api("/rooms", {
    method: "POST", authenticated,
    body: {name: fields.name.trim() || null, mode: fields.mode, is_private: Boolean(password), password},
  });
  location.assign(roomUrl(room.code));
});

onForm("password-form", async fields => {
  await api("/me/password", { method: "POST", authenticated, body: fields });
  message("Đã đổi mật khẩu.");
  await load();
});

element("logout").addEventListener("click", async () => {
  await logout().catch(() => {});
});

async function load() {
  const profile = await api("/me", { authenticated });
  element("profile").textContent = profile.display_name;
  element("password-panel").hidden = !profile.must_change_password;
  element("join-tab").parentElement.hidden = profile.must_change_password;
  if (profile.must_change_password) {
    element("join-panel").hidden = true;
    element("create-panel").hidden = true;
    element("presence-state").textContent = "Cần đổi mật khẩu";
  } else {
    selectTab(tabs.find(tab => tab.getAttribute("aria-selected") === "true") || tabs[0]);
  }
  if (profile.is_guest) element("presence-state").textContent = "Đang dùng tên khách";
  if (profile.is_guest || profile.must_change_password) return;
  if (!presence) {
    presence = window.io({
      transports: ["websocket"],
      auth: done => accessToken().then(token => done({token}), () => done({})),
    });
    presence.on("connect", () => { element("presence-state").textContent = "Đã kết nối"; });
    presence.on("disconnect", () => { element("presence-state").textContent = "Đang kết nối lại…"; });
    presence.on("connect_error", () => { element("presence-state").textContent = "Kết nối tạm gián đoạn"; });
    presence.on("force_disconnect", ({reason}) => {
      presence.disconnect();
      sessionEnded(reason === "DEVICE_SESSION_REPLACED"
        ? "Tài khoản đã được chuyển sang thiết bị khác."
        : "Phiên đã bị thu hồi. Vui lòng đăng nhập lại.");
    });
    window.addEventListener("pagehide", () => presence.disconnect());
  }
  element("create-tab").hidden = false;
  const rooms = await api("/rooms/mine", { authenticated });
  const list = element("mine");
  list.replaceChildren();
  for (const room of rooms) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = roomUrl(room.code);
    link.textContent = room.name ? room.name + " · " + room.code : room.code;
    item.append(link);
    list.append(item);
  }
  element("mine-panel").hidden = false;
  element("no-rooms").hidden = rooms.length !== 0;
}

if (await requireSession()) {
  try {
    const config = await api("/config/public").catch(() => null);
    applyBranding(config);
    if (config) {
      const mode = element("create-form").elements.mode;
      mode.options[0].disabled = config.meeting_enabled === false;
      mode.options[1].disabled = config.livestream_enabled === false;
      if (mode.selectedOptions[0].disabled && !mode.options[1].disabled) mode.value = "livestream";
      if (config.maintenance_mode || (mode.options[0].disabled && mode.options[1].disabled)) {
        element("create-form").querySelector("button").disabled = true;
        message(config.maintenance_message || "Tạo phòng đang bảo trì.");
      }
    }
    await load();
  } catch (error) {
    if (error.status === 401) location.replace("/");
    else message(error.message, true);
  }
}
