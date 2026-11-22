import { initDialogs } from "/client/js/app/components/primitives.js";

initDialogs();
const dialog = document.getElementById("admin-confirm");
let pending;
document.addEventListener("htmx:confirm", event => {
  if (!event.detail.question) return;
  event.preventDefault();
  if (dialog.open) return;
  pending = event.detail.issueRequest;
  document.getElementById("admin-confirm-description").textContent = event.detail.question;
  dialog.showModal();
});
document.getElementById("admin-confirm-submit").addEventListener("click", () => {
  const request = pending;
  pending = undefined;
  dialog.close();
  request?.(true);
});
dialog.addEventListener("close", () => { pending = undefined; });
document.addEventListener("htmx:beforeRequest", event => {
  const polling = event.detail.elt;
  if (!polling.matches("#live-rooms-list, #dashboard-summary")) return;
  if (document.hidden || dialog.open || polling.contains(document.activeElement) ||
      polling.querySelector("details[open]")) event.preventDefault();
});
