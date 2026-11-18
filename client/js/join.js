import { api } from "./api.js";
import { element, onForm, roomUrl } from "./ui.js";
import { loadWorkspace } from "./workspace.js";
import { vi } from "./app/i18n/vi.js";

if (await loadWorkspace()) {
  element("join-form").hidden = false;
  onForm("join-form", async fields => {
    const code = fields.code.trim().toLowerCase();
    if (!/^[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(code)) throw new Error(vi.invalidRoomCode);
    const room = await api("/rooms/" + code, {authenticated: true});
    if (room.status === "closed") throw new Error(vi.roomClosed);
    location.assign(roomUrl(code));
  });
}
