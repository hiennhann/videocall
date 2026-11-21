import { api } from "./api.js";
import { element, message } from "./ui.js";
import { action, roomCard } from "./room-cards.js";
import { initDialogs } from "./app/components/primitives.js";
import { loadWorkspace } from "./workspace.js";

const state = await loadWorkspace();
if (state) {
  initDialogs();
  const dialog = element("close-room-dialog");
  let selected;
  const list = element("mine");
  const confirm = element("confirm-close-room");
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    try {
      await api(`/rooms/${selected.code}`, {method: "DELETE", authenticated: true});
      selected.card.remove();
      element("no-rooms").hidden = list.childElementCount > 0;
      dialog.close();
      element("page-title").focus();
      message("Đã đóng phòng.");
    } catch (error) {
      dialog.close();
      message(error.message, true);
    } finally {
      confirm.disabled = false;
    }
  });
  try {
    const rooms = state.profile.is_guest ? [] : await api("/rooms/mine", {authenticated: true});
    for (const room of rooms) {
      const copy = action("Sao chép mã", async () => {
        try { await navigator.clipboard.writeText(room.code); message("Đã sao chép mã phòng."); }
        catch { message(`Mã phòng: ${room.code}`); }
      });
      const close = action("Đóng phòng", () => {
        selected = {code: room.code, card};
        element("close-room-description").textContent = `Kết thúc cuộc gọi trong “${room.name || room.code}”.`;
        dialog.showModal();
      }, "danger");
      const card = roomCard(room, [copy, close]);
      list.append(card);
    }
    element("no-rooms").hidden = rooms.length !== 0;
    element("mine-panel").hidden = false;
  } catch (error) {
    message(error.message, true);
  }
}
