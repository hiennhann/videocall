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
    const mode = form.elements.mode;
    const capacity = form.elements.max_participants;
    if (config) {
      for (const option of capacity.options) {
        if (Number(option.value) > config.max_participants_per_room) option.disabled = true;
      }
      mode.options[0].disabled = config.meeting_enabled === false;
      mode.options[1].disabled = config.livestream_enabled === false;
      if (mode.selectedOptions[0].disabled && !mode.options[1].disabled) mode.value = "livestream";
      if (config.maintenance_mode || (mode.options[0].disabled && mode.options[1].disabled)) {
        form.querySelector("button").disabled = true;
        message(config.maintenance_message || vi.roomMaintenance);
      }
    }
    function showCapacity() {
      capacity.disabled = mode.value !== "meeting";
      element("capacity-label").hidden = capacity.disabled;
    }
    mode.addEventListener("change", showCapacity);
    showCapacity();
    onForm("create-form", async fields => {
      const password = fields.password || null;
      const room = await api("/rooms", {
        method: "POST", authenticated: true,
        body: {name: fields.name.trim() || null, mode: fields.mode, is_private: Boolean(password), password,
          max_participants: fields.max_participants ? Number(fields.max_participants) : null},
      });
      location.assign(roomUrl(room.code));
    });
    form.hidden = false;
  }
}
