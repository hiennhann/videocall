import { api, clearSession, restoreSession, saveSession, takeSessionNotice } from "./api.js";
import { element, message, onForm } from "./ui.js";
import { applyBranding } from "./theme.js";
import { initDialogs, initTabs } from "./app/components/primitives.js";
import { loginDestination } from "./auth-navigation.js";

initDialogs();
initTabs();

const registerPassword = element("register-form").elements.password;
function showPasswordStrength() {
  const value = registerPassword.value;
  element("password-strength").hidden = !value;
  const variety = [/[a-z]/i, /\d/, /[^\p{L}\p{N}\s]/u].filter(pattern => pattern.test(value)).length;
  const score = value.trim().length < registerPassword.minLength ? 0 :
    value.length >= 16 || (value.length >= 12 && variety >= 2) ? 3 : variety >= 2 ? 2 : 1;
  element("password-meter").value = score;
  element("password-strength-text").textContent = ["Chưa đủ dài", "Yếu", "Trung bình", "Mạnh"][score];
}
registerPassword.addEventListener("input", showPasswordStrength);

function authForm(id, handler) {
  const form = element(id);
  function clearErrors() {
    for (const note of form.querySelectorAll("[data-field-error]")) {
      const input = note.previousElementSibling;
      input.removeAttribute("aria-invalid");
      const ids = input.getAttribute("aria-describedby").split(" ").filter(id => id !== note.id);
      if (ids.length) input.setAttribute("aria-describedby", ids.join(" "));
      else input.removeAttribute("aria-describedby");
      note.remove();
    }
  }
  form.addEventListener("input", clearErrors);
  onForm(id, async (fields, form) => {
    clearErrors();
    try {
      await handler(fields, form);
    } catch (error) {
      for (const [name, description] of Object.entries(error.details?.fields ?? {})) {
        const input = form.elements.namedItem(name);
        if (!(input instanceof HTMLInputElement)) continue;
        const note = document.createElement("span");
        note.id = `${id}-${name}-error`;
        note.dataset.fieldError = "";
        note.className = "field-error text-small";
        note.textContent = description;
        input.after(note);
        input.setAttribute("aria-invalid", "true");
        input.setAttribute("aria-describedby", [input.getAttribute("aria-describedby"), note.id].filter(Boolean).join(" "));
      }
      throw error;
    }
  });
}

const transfer = element("device-transfer");
const destination = loginDestination(new URLSearchParams(location.search).get("next"));
if (new URLSearchParams(location.search).get("login_required") === "1") clearSession();
let pendingTransfer;
const notice = takeSessionNotice();
if (notice) message(notice);
else if (await restoreSession()) location.replace(destination);

async function signIn(path, body) {
  saveSession(await api(path, { method: "POST", body }));
  location.assign(destination);
}

authForm("account-form", async fields => {
  try {
    await signIn("/auth/login", {...fields, client_type: "web"});
  } catch (error) {
    if (error.code !== "DEVICE_TRANSFER_REQUIRED") throw error;
    pendingTransfer = error.details.transfer_token;
    transfer.showModal();
  }
});

async function finishTransfer(action) {
  if (!pendingTransfer) return;
  const token = pendingTransfer;
  pendingTransfer = undefined;
  const confirm = element("transfer-confirm");
  const cancel = element("transfer-cancel");
  confirm.disabled = cancel.disabled = true;
  try {
    const result = await api("/auth/device-transfer/" + action, {
      method: "POST", body: {transfer_token: token, client_type: "web"},
    });
    if (action === "confirm") {
      saveSession(result);
      location.assign(destination);
    }
  } catch (error) {
    message(error.message, true);
  } finally {
    transfer.close();
    confirm.disabled = cancel.disabled = false;
    element("account-form").elements.password.value = "";
  }
}

element("transfer-confirm").addEventListener("click", () => finishTransfer("confirm"));
element("transfer-cancel").addEventListener("click", () => finishTransfer("cancel"));
transfer.addEventListener("cancel", event => {
  event.preventDefault();
  finishTransfer("cancel");
});
authForm("guest-form", fields => signIn("/auth/guest", {...fields, client_type: "web"}));
authForm("register-form", async (fields, form) => {
  await api("/auth/register", { method: "POST", body: fields });
  element("account-form").elements.email.value = fields.email;
  form.reset();
  showPasswordStrength();
  element("login-tab").click();
  element("account-form").elements.password.focus();
  message("Đã tạo tài khoản. Bạn có thể đăng nhập.");
});

try {
  const config = await api("/config/public");
  applyBranding(config);
  element("register-tab").hidden = !config.allow_registration;
  element("guest-panel").hidden = !config.allow_guest || config.maintenance_mode;
  registerPassword.minLength = config.password_min_length;
  element("password-help").textContent = `Ít nhất ${config.password_min_length} ký tự.`;
  if (config.maintenance_mode) message(config.maintenance_message || "Hệ thống đang bảo trì.");
} catch (error) {
  message(error.message, true);
}
