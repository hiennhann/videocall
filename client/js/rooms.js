import { api } from "./api.js";
import { element, message, roomUrl } from "./ui.js";
import { loadWorkspace } from "./workspace.js";

const state = await loadWorkspace();
if (state) {
  try {
    const rooms = state.profile.is_guest ? [] : await api("/rooms/mine", {authenticated: true});
    const list = element("mine");
    for (const room of rooms) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = roomUrl(room.code);
      const name = document.createElement("strong");
      name.textContent = room.name || room.code;
      const code = document.createElement("small");
      code.textContent = room.code;
      link.append(name, code);
      item.append(link);
      list.append(item);
    }
    element("no-rooms").hidden = rooms.length !== 0;
    element("mine-panel").hidden = false;
  } catch (error) {
    message(error.message, true);
  }
}
