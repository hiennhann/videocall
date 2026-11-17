let target;
let source;

function close() {
  source?.close();
  source = undefined;
  target = undefined;
}

function sync() {
  const current = document.querySelector("[data-live-dashboard]");
  if (current === target) return;
  close();
  if (!current) return;
  target = current;
  const status = current.querySelector("[data-dashboard-status]");
  source = new EventSource("/admin/dashboard/events");
  source.onmessage = ({data}) => {
    const counts = JSON.parse(data);
    current.querySelector("[data-active-rooms]").textContent = counts.rooms_with_participants;
    current.querySelector("[data-online-accounts]").textContent = counts.online_accounts;
    status.textContent = "Đang cập nhật trực tiếp";
  };
  source.onerror = () => { status.textContent = "Đang kết nối lại…"; };
  source.addEventListener("session-ended", () => {
    close();
    location.replace("/admin/login");
  });
}

document.addEventListener("htmx:afterSwap", sync);
window.addEventListener("pagehide", close);
window.addEventListener("pageshow", sync);
sync();
