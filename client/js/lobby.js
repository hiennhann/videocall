import { accessToken, api, logout, requireSession, sessionEnded } from "./api.js";
import { element, message, onForm, roomUrl } from "./ui.js";
import { applyBranding } from "./theme.js";

const authenticated = true;
let presence;

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
  element("join-form").closest("section").hidden = profile.must_change_password;
  if (profile.is_guest || profile.must_change_password) return;
  if (!presence) {
    presence = window.io({
      transports: ["websocket"],
      auth: done => accessToken().then(token => done({token}), () => done({})),
    });
    presence.on("force_disconnect", ({reason}) => {
      presence.disconnect();
      sessionEnded(reason === "DEVICE_SESSION_REPLACED"
        ? "Tài khoản đã được chuyển sang thiết bị khác."
        : "Phiên đã bị thu hồi. Vui lòng đăng nhập lại.");
    });
    window.addEventListener("pagehide", () => presence.disconnect());
  }
  element("create-panel").hidden = false;
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
  element("mine-panel").hidden = rooms.length === 0;
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
