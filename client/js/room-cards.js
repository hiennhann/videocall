import { message, roomUrl } from "./ui.js";

export function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text != null) result.textContent = text;
  if (className) result.className = className;
  return result;
}

export function action(text, handler, className = "secondary") {
  const button = node("button", text, className);
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await handler(button); }
    catch (error) { message(error.message, true); }
    finally { button.disabled = false; }
  });
  return button;
}

export function roomCard(room, extraActions = [], destination = roomUrl(room.code)) {
  const card = node("li", null, "room-card");
  const title = node("h3", room.name || room.code);
  const metadata = node("p", [
    room.mode === "livestream" ? "Livestream" : "Gọi nhóm",
    room.is_private || room.has_password ? "Có mật khẩu" : null,
    Number.isInteger(room.participants) ? `${room.participants}/${room.max_participants} người` : null,
  ].filter(Boolean).join(" · "), "muted text-small");
  const controls = node("div", null, "controls");
  const enter = node("a", "Vào phòng", "button");
  enter.href = destination;
  controls.append(enter, ...extraActions);
  card.append(node("span", "Đang mở", "status-pill"), title, metadata, node("code", room.code), controls);
  return card;
}
