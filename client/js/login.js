import { api, saveSession, session } from "./api.js";
import { element, message, onForm } from "./ui.js";

if (session()) location.replace("/lobby");

async function signIn(path, body) {
  saveSession(await api(path, { method: "POST", body }));
  location.assign("/lobby");
}

onForm("account-form", fields => signIn("/auth/login", fields));
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
  element("register-panel").hidden = !config.allow_registration;
  element("guest-panel").hidden = !config.allow_guest || config.maintenance_mode;
  element("register-form").elements.password.minLength = config.password_min_length;
  if (config.maintenance_mode) message(config.maintenance_message || "Hệ thống đang bảo trì.");
} catch (error) {
  message(error.message, true);
}
