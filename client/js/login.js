import { api, restoreSession, saveSession, takeSessionNotice } from "./api.js";
import { element, message, onForm } from "./ui.js";
import { applyBranding } from "./theme.js";
import { initDialogs } from "./app/components/primitives.js";
import { loginDestination } from "./auth-navigation.js";

initDialogs();

const transfer = element("device-transfer");
const destination = loginDestination(new URLSearchParams(location.search).get("next"));
let pendingTransfer;
const notice = takeSessionNotice();
if (notice) message(notice);
else if (await restoreSession()) location.replace(destination);

async function signIn(path, body) {
  saveSession(await api(path, { method: "POST", body }));
  location.assign(destination);
}

onForm("account-form", async fields => {
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
onForm("guest-form", fields => signIn("/auth/guest", fields));
onForm("register-form", async (fields, form) => {
  await api("/auth/register", { method: "POST", body: fields });
  element("account-form").elements.email.value = fields.email;
  form.reset();
  element("register-panel").open = false;
  message("Đã tạo tài khoản. Bạn có thể đăng nhập.");
});

try {
  const config = await api("/config/public");
  applyBranding(config);
  element("register-panel").hidden = !config.allow_registration;
  element("guest-panel").hidden = !config.allow_guest || config.maintenance_mode;
  element("register-form").elements.password.minLength = config.password_min_length;
  if (config.maintenance_mode) message(config.maintenance_message || "Hệ thống đang bảo trì.");
} catch (error) {
  message(error.message, true);
}
