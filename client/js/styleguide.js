import { translate, vi } from "./app/i18n/vi.js";
import { icon, initDialogs, initDropdowns, initTabs, setAvatar } from "./app/components/primitives.js";

translate();
initDialogs();
initDropdowns();
initTabs();

const themeSelect = document.getElementById("theme");
const preference = window.matchMedia("(prefers-color-scheme: dark)");
const themeKey = "videocall.styleguide.theme";
try {
  const saved = localStorage.getItem(themeKey);
  if (["light", "dark", "system"].includes(saved)) themeSelect.value = saved;
} catch { /* The preview still works when storage is unavailable. */ }

const swatches = [
  ["bg-app", "bg"], ["surface", "surface"], ["surface-2", "surface2"],
  ["text", "text"], ["text-muted", "muted"], ["primary", "primary"],
  ["primary-soft", "soft"], ["success", "success"], ["warning", "warning"],
  ["danger", "danger"], ["border-control", "border"], ["focus", "focus"],
];
for (const [token, className] of swatches) {
  const swatch = document.createElement("div");
  swatch.className = `guide-swatch swatch-${className}`;
  const color = document.createElement("div");
  color.className = "guide-swatch__color";
  const meta = document.createElement("div");
  meta.className = "guide-swatch__meta";
  const name = document.createElement("code");
  name.textContent = `--${token}`;
  const value = document.createElement("code");
  value.dataset.token = token;
  meta.append(name, value);
  swatch.append(color, meta);
  document.getElementById("palette").append(swatch);
}
function applyTheme() {
  document.documentElement.dataset.theme = themeSelect.value === "system" ? (preference.matches ? "dark" : "light") : themeSelect.value;
  const styles = getComputedStyle(document.documentElement);
  for (const value of document.querySelectorAll("[data-token]")) {
    value.textContent = styles.getPropertyValue(`--${value.dataset.token}`).trim().toUpperCase();
  }
}
themeSelect.addEventListener("change", () => {
  applyTheme();
  try { localStorage.setItem(themeKey, themeSelect.value); } catch { /* Optional persistence. */ }
});
preference.addEventListener("change", applyTheme);
applyTheme();

for (const name of ["video", "plus", "check", "close", "info", "alert", "arrow", "chevron", "home", "users", "message", "settings", "history", "bell", "search", "loader", "mic", "sun"]) {
  const tile = document.createElement("div");
  tile.className = "guide-icon";
  const label = document.createElement("code");
  label.textContent = name;
  tile.append(icon(name), label);
  document.getElementById("icons").append(tile);
}
for (const node of document.querySelectorAll("[data-user]")) {
  const name = vi[node.dataset.name];
  setAvatar(node, node.dataset.user, name);
  if (node.hasAttribute("data-online")) {
    const indicator = document.createElement("span");
    indicator.className = "avatar__online";
    indicator.setAttribute("aria-hidden", "true");
    node.append(indicator);
    node.setAttribute("aria-label", `${name} · ${vi.online}`);
  }
}

function toast(message, type = "info") {
  const returnFocus = document.activeElement;
  const stack = document.getElementById("toasts");
  if (stack.childElementCount === 3) stack.firstElementChild.remove();
  const notice = document.createElement("div");
  notice.className = `toast toast--${type}`;
  const text = document.createElement("p");
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "button button--ghost button--icon";
  close.setAttribute("aria-label", vi.dismiss);
  close.append(icon("close"));
  close.addEventListener("click", () => {
    const focused = notice.contains(document.activeElement);
    notice.remove();
    if (focused && returnFocus.isConnected && !returnFocus.closest("dialog:not([open]), [hidden]")) returnFocus.focus();
  });
  notice.append(icon(type === "success" ? "check" : type === "danger" ? "alert" : "info"), text, close);
  stack.append(notice);
}
for (const button of document.querySelectorAll("[data-toast]")) {
  button.addEventListener("click", () => {
    const type = button.dataset.toast;
    toast(vi[type === "success" ? "successMessage" : type === "danger" ? "errorMessage" : "infoMessage"], type);
    const dropdown = button.closest("details");
    if (dropdown) {
      dropdown.open = false;
      dropdown.querySelector("summary").focus();
    }
  });
}
document.getElementById("confirm-demo").addEventListener("click", () => {
  document.getElementById("sample-modal").close();
  toast(vi.modalResult, "success");
});

const roomName = document.getElementById("room-name");
function validateRoom() {
  const valid = Boolean(roomName.value.trim());
  roomName.setAttribute("aria-invalid", String(!valid));
  document.getElementById("room-error").hidden = valid;
  return valid;
}
roomName.addEventListener("input", () => {
  if (roomName.hasAttribute("aria-invalid")) validateRoom();
});
document.getElementById("sample-form").addEventListener("submit", event => {
  event.preventDefault();
  if (validateRoom()) toast(vi.formSuccess, "success");
  else roomName.focus();
});

let inviteInterval;
let inviteDeadline;
const inviteTimer = document.getElementById("invite-timer");
const inviteActions = [document.getElementById("accept-invite"), document.getElementById("decline-invite")];
function updateInvite() {
  const seconds = Math.max(0, Math.ceil((inviteDeadline - Date.now()) / 1000));
  inviteTimer.textContent = seconds ? vi.inviteRemaining.replace("{seconds}", seconds) : vi.inviteExpired;
  if (!seconds) {
    clearInterval(inviteInterval);
    if (inviteActions.includes(document.activeElement)) document.getElementById("start-invite").focus();
    inviteActions.forEach(button => { button.disabled = true; });
    document.getElementById("invite-result").textContent = vi.inviteExpired;
  }
}
document.getElementById("start-invite").addEventListener("click", () => {
  clearInterval(inviteInterval);
  inviteDeadline = Date.now() + 30000;
  document.getElementById("invite-demo").hidden = false;
  document.getElementById("invite-result").textContent = vi.inviteBody;
  inviteActions.forEach(button => { button.disabled = false; });
  updateInvite();
  inviteInterval = setInterval(updateInvite, 1000);
});
inviteActions.forEach((button, index) => button.addEventListener("click", () => {
  clearInterval(inviteInterval);
  document.getElementById("invite-demo").hidden = true;
  document.getElementById("start-invite").focus();
  toast(vi[index === 0 ? "inviteAccepted" : "inviteDeclined"]);
}));
window.addEventListener("pagehide", () => clearInterval(inviteInterval));

const navLinks = document.querySelectorAll(".guide-nav a");
for (const link of navLinks) link.addEventListener("click", () => {
  navLinks.forEach(item => item.removeAttribute("aria-current"));
  link.setAttribute("aria-current", "location");
});
