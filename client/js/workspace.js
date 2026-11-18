import { accessToken, api, logout, requireSession, sessionEnded } from "./api.js";
import { element, message } from "./ui.js";
import { applyBranding } from "./theme.js";
import { vi } from "./app/i18n/vi.js";
import { loginUrl } from "./auth-navigation.js";

let presence;

element("logout").addEventListener("click", () => logout().catch(() => {}));

export async function loadWorkspace() {
  if (!await requireSession()) return null;
  try {
    const profile = await api("/me", {authenticated: true});
    if (profile.must_change_password && document.body.dataset.page !== "account") {
      location.replace("/account");
      return null;
    }
    const config = await api("/config/public").catch(() => null);
    applyBranding(config);
    for (const name of document.querySelectorAll("[data-display-name]")) name.textContent = profile.display_name;
    for (const item of document.querySelectorAll("[data-member-only]")) item.hidden = profile.is_guest;
    const status = element("presence-state");
    if (profile.must_change_password) {
      status.textContent = vi.passwordRequired;
    } else if (profile.is_guest) {
      status.textContent = vi.guestSession;
    } else if (!presence) {
      presence = window.io({
        transports: ["websocket"],
        auth: done => accessToken().then(token => done({token}), () => done({})),
      });
      presence.on("connect", () => { status.textContent = vi.connected; });
      presence.on("disconnect", () => { status.textContent = vi.reconnecting; });
      presence.on("connect_error", () => { status.textContent = vi.connectionInterrupted; });
      presence.on("force_disconnect", ({reason}) => {
        presence.disconnect();
        sessionEnded(reason === "DEVICE_SESSION_REPLACED" ? vi.sessionReplaced : vi.sessionRevoked);
      });
      window.addEventListener("pagehide", () => presence.disconnect());
      window.addEventListener("pageshow", event => { if (event.persisted) presence.connect(); });
    }
    return {profile, config};
  } catch (error) {
    if (error.status === 401) location.replace(loginUrl());
    else message(error.message, true);
    return null;
  }
}
