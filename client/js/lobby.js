import { api, logout, requireSession } from "./api.js";
import { element, message, onForm, roomUrl } from "./ui.js";

const authenticated = true;

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
    body: {name: fields.name.trim() || null, max_participants: 2, is_private: Boolean(password), password},
  });
  location.assign(roomUrl(room.code));
});

onForm("password-form", async fields => {
  await api("/me/password", { method: "POST", authenticated, body: fields });
  message("Đã đổi mật khẩu.");
  await load();
});

element("logout").addEventListener("click", async () => {
  try {
    await logout();
  } finally {
    location.assign("/");
  }
});

async function load() {
  const profile = await api("/me", { authenticated });
  element("profile").textContent = profile.display_name;
  element("password-panel").hidden = !profile.must_change_password;
  element("join-form").closest("section").hidden = profile.must_change_password;
  if (profile.is_guest || profile.must_change_password) return;
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

if (requireSession()) {
  try {
    await load();
  } catch (error) {
    if (error.status === 401) location.replace("/");
    else message(error.message, true);
  }
}
