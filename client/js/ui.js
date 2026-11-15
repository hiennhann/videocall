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
