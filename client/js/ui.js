export const element = id => document.getElementById(id);

export function message(text, error = false) {
  const notice = element("message");
  notice.textContent = text;
  notice.classList.toggle("error", error);
  notice.hidden = !text;
}

export function onForm(id, handler) {
  element(id).addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = Object.fromEntries(new FormData(form));
    const button = form.querySelector("button[type=submit], button:not([type])");
    button.disabled = true;
    message("");
    try {
      await handler(fields, form);
    } catch (error) {
      message(error.message || "Đã xảy ra lỗi.", true);
    } finally {
      button.disabled = false;
    }
  });
}

export function roomUrl(code) {
  return "/room?" + new URLSearchParams({code});
}

export function openInvite(invite) {
  sessionStorage.setItem("videocall.room-invite", JSON.stringify({code: invite.room.code, id: invite.id}));
  location.assign(roomUrl(invite.room.code));
}

export function takeInvite(code) {
  const raw = sessionStorage.getItem("videocall.room-invite");
  if (!raw) return null;
  sessionStorage.removeItem("videocall.room-invite");
  try {
    const invite = JSON.parse(raw);
    return invite.code === code ? invite.id : null;
  } catch { return null; }
}
