import { api, accessToken } from "./api.js";
import { node } from "./room-cards.js";
import { roomUrl } from "./ui.js";
import { setAvatar } from "./app/components/primitives.js";

export const auth = {authenticated: true};
export const apiWrite = (path, method, body) => api(path, {...auth, method, body});
export const dateTime = new Intl.DateTimeFormat("vi-VN", {dateStyle: "short", timeStyle: "short"});

export function personAvatar(user, size = 40) {
  if (/^\/media\/avatars\/[0-9a-f-]{36}\/[0-9a-f]{64}-(64|256)\.webp$/i.test(user?.avatar_url ?? "")) {
    const img = document.createElement("img");
    img.src = user.avatar_url;
    img.className = "profile-avatar";
    img.alt = "";
    img.width = img.height = size;
    img.loading = "lazy";
    return img;
  }
  const span = node("span", null, size === 96 ? "avatar avatar-large" : "avatar");
  setAvatar(span, user?.id, user?.display_name || "Videocall");
  span.removeAttribute("role");
  span.removeAttribute("aria-label");
  span.setAttribute("aria-hidden", "true");
  return span;
}

export function personRow(user, caption, controls = []) {
  const row = node("li", null, "panel person-row");
  const copy = node("div", null, "person-copy");
  copy.append(node("strong", user.display_name));
  if (caption) copy.append(node("p", caption, "muted text-small"));
  const actions = node("div", null, "controls");
  actions.append(...controls);
  row.append(personAvatar(user), copy, actions);
  return row;
}

export async function allPages(path) {
  const items = [];
  for (let page = 1; ; page++) {
    const result = await api(`${path}${path.includes("?") ? "&" : "?"}page=${page}&page_size=100`, auth);
    items.push(...result.items);
    if (items.length >= result.total || !result.items.length) return items;
  }
}

export async function quickCall(userId) {
  const room = await apiWrite("/rooms", "POST", {mode: "meeting", name: null, is_private: false});
  sessionStorage.setItem("videocall.quick-invite", JSON.stringify({code: room.code, userId}));
  location.assign(roomUrl(room.code));
}

export async function downloadChat(code) {
  const url = `/api/v1/me/call-history/${encodeURIComponent(code)}/chat-export`;
  const get = async refresh => fetch(url, {
    headers: {Authorization: `Bearer ${await accessToken(refresh)}`}, cache: "no-store",
  });
  let response = await get(false);
  if (response.status === 401) response = await get(true);
  if (!response.ok) throw new Error("Hiện không tải được nhật ký chat cho phòng này.");
  const href = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = `chat-${code}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
