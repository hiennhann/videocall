import { api, logout } from "./api.js";
import { initTabs } from "./app/components/primitives.js";
import { inviteSoundKey } from "./notifications.js";
import { apiWrite, personAvatar } from "./social-ui.js";
import { element, message, onForm } from "./ui.js";
import { loadWorkspace } from "./workspace.js";
import { vi } from "./app/i18n/vi.js";

const state = await loadWorkspace();
if (state) {
  let profile = state.profile;
  const config = state.config;
  const profileForm = element("profile-form");
  const privacyForm = element("privacy-form");
  const passwordForm = element("password-form");
  const avatarForm = element("avatar-form");
  let previewUrl;
  const preview = element("avatar-preview");
  const minimum = config?.password_min_length || 8;
  const limit = config?.avatar_max_kb || 2048;
  initTabs();
  function refresh() {
    element("profile").textContent = profile.display_name;
    element("profile-email").textContent = profile.email || vi.guestSession;
    element("profile-role").textContent = profile.is_guest ? vi.guestRole : profile.role === "admin" ? vi.adminRole : vi.memberRole;
    element("account-panel").hidden = false;
    element("account-settings").hidden = profile.is_guest;
    if (profile.is_guest) return;
    profileForm.elements.display_name.value = profile.display_name;
    profileForm.elements.birth_date.value = profile.birth_date || "";
    profileForm.elements.email.value = profile.email;
    profileForm.elements.birth_date.max = new Intl.DateTimeFormat("sv-SE").format(new Date());
    privacyForm.elements.discoverable_by_email.checked = profile.privacy.discoverable_by_email;
    privacyForm.elements.show_online_status.checked = profile.privacy.show_online_status;
    element("profile-avatar").replaceChildren(personAvatar(profile, 96));
    element("remove-avatar").hidden = !profile.avatar_url;
    avatarForm.elements.file.disabled = config?.allow_avatar_upload === false;
    avatarForm.querySelector("[type=submit]").disabled = config?.allow_avatar_upload === false;
    element("avatar-help").textContent = config?.allow_avatar_upload === false ?
      "Quản trị viên đã tắt tải ảnh." : `JPEG, PNG hoặc WebP, tối đa ${limit} KB.`;
  }
  function protect() {
    for (const id of ["profile-settings-tab", "privacy-tab", "logout-all"]) {
      element(id).hidden = profile.must_change_password;
    }
    if (profile.must_change_password) {
      element("security-tab").click();
      message(vi.passwordRequired);
    }
  }
  function changed(form) {
    const fields = form.elements;
    if (form === profileForm) return fields.display_name.value.trim() !== profile.display_name ||
      fields.birth_date.value !== (profile.birth_date || "");
    return fields.discoverable_by_email.checked !== profile.privacy.discoverable_by_email ||
      fields.show_online_status.checked !== profile.privacy.show_online_status;
  }
  function updateSave(form) { form.querySelector("button").disabled = !changed(form); }
  function unsetPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = undefined;
    preview.removeAttribute("src");
    preview.hidden = true;
  }

  refresh();
  if (!profile.is_guest) {
    protect();
    for (const form of [profileForm, privacyForm]) {
      form.addEventListener("input", () => updateSave(form));
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!changed(form)) return;
        form.inert = true;
        try {
          const fields = form.elements;
          const patch = form === profileForm ? {display_name: fields.display_name.value.trim(),
            birth_date: fields.birth_date.value || null} : {privacy: {
            discoverable_by_email: fields.discoverable_by_email.checked,
            show_online_status: fields.show_online_status.checked,
          }};
          profile = await apiWrite("/me", "PATCH", patch);
          refresh();
          message("Đã lưu thay đổi.");
        } catch (error) { message(error.message, true); }
        finally { form.inert = false; updateSave(form); }
      });
    }
    passwordForm.elements.new_password.minLength = minimum;
    passwordForm.elements.new_password.addEventListener("input", event => {
      const length = event.target.value.length;
      element("new-password-meter").value = length < minimum ? 0 : length >= 16 ? 3 : length >= 12 ? 2 : 1;
    });
    onForm("password-form", async ({current_password, new_password, confirm_password}, form) => {
      if (new_password !== confirm_password) throw new Error("Hai mật khẩu mới chưa khớp.");
      await apiWrite("/me/password", "POST", {current_password, new_password});
      form.reset();
      element("new-password-meter").value = 0;
      profile = (await loadWorkspace()).profile;
      refresh();
      protect();
      message(vi.passwordChanged);
    });
    onForm("avatar-form", async (_, form) => {
      const file = form.elements.file.files[0];
      if (!file || file.size > limit * 1024) throw new Error(`Ảnh phải nhỏ hơn hoặc bằng ${limit} KB.`);
      profile = await apiWrite("/me/avatar", "PUT", new FormData(form));
      form.reset();
      unsetPreview();
      refresh();
      message("Đã cập nhật ảnh đại diện.");
    });
    avatarForm.elements.file.addEventListener("change", () => {
      unsetPreview();
      const file = avatarForm.elements.file.files[0];
      if (!file) return;
      if (file.size > limit * 1024) { message(`Ảnh vượt quá ${limit} KB.`, true); return; }
      if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) return;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      preview.hidden = false;
    });
    window.addEventListener("pagehide", unsetPreview);
    element("remove-avatar").addEventListener("click", async () => {
      if (!window.confirm("Gỡ ảnh đại diện hiện tại?")) return;
      try {
        await apiWrite("/me/avatar", "DELETE");
        profile.avatar_url = profile.avatar_thumb_url = null;
        refresh();
        message("Đã gỡ ảnh đại diện.");
      } catch (error) { message(error.message, true); }
    });
    element("logout-all").addEventListener("click", async () => {
      if (!window.confirm("Đăng xuất mọi phiên, kể cả thiết bị này?")) return;
      try { await api("/auth/logout-all", {authenticated: true, method: "POST"}); await logout(); }
      catch (error) { message(error.message, true); }
    });
    const sound = element("invite-sound");
    sound.checked = localStorage.getItem(inviteSoundKey) === "true";
    sound.addEventListener("change", () => localStorage.setItem(inviteSoundKey, String(sound.checked)));
  }
}
