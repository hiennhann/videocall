import { api } from "./api.js";
import { element, message, onForm, roomUrl } from "./ui.js";
import { loadWorkspace } from "./workspace.js";
import { vi } from "./app/i18n/vi.js";

const state = await loadWorkspace();
if (state) {
  if (state.profile.is_guest) {
    message(vi.guestCannotCreate, true);
  } else {
    const form = element("create-form");
    const config = state.config;
    if (config) {
      const mode = form.elements.mode;
      mode.options[0].disabled = config.meeting_enabled === false;
      mode.options[1].disabled = config.livestream_enabled === false;
      if (mode.selectedOptions[0].disabled && !mode.options[1].disabled) mode.value = "livestream";
      if (config.maintenance_mode || (mode.options[0].disabled && mode.options[1].disabled)) {
        form.querySelector("button").disabled = true;
        message(config.maintenance_message || vi.roomMaintenance);
      }
    }
    onForm("create-form", async fields => {
      const password = fields.password || null;
      const room = await api("/rooms", {
        method: "POST", authenticated: true,
        body: {name: fields.name.trim() || null, mode: fields.mode, is_private: Boolean(password), password},
      });
      location.assign(roomUrl(room.code));
    });
    form.hidden = false;
  }
}
