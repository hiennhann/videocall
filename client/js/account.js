import { api } from "./api.js";
import { element, message, onForm } from "./ui.js";
import { loadWorkspace } from "./workspace.js";
import { vi } from "./app/i18n/vi.js";

const state = await loadWorkspace();
if (state) {
  const profile = state.profile;
  element("profile").textContent = profile.display_name;
  element("profile-email").textContent = profile.email || vi.guestSession;
  element("profile-role").textContent = profile.is_guest ? vi.guestRole : profile.role === "admin" ? vi.adminRole : vi.memberRole;
  element("account-panel").hidden = false;
  element("password-panel").hidden = profile.is_guest;
  if (profile.must_change_password) message(vi.passwordRequired);
  if (state.config) element("password-form").elements.new_password.minLength = state.config.password_min_length;
  onForm("password-form", async (fields, form) => {
    await api("/me/password", {method: "POST", authenticated: true, body: fields});
    form.reset();
    message(vi.passwordChanged);
    await loadWorkspace();
  });
}
