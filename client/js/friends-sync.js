import { api } from "./api.js";

// Snapshot HTTP bù các thông báo best-effort bị mất khi socket ngắt kết nối.
export function bindFriendsSync(socket) {
  let revision = 0;
  let loading = false;
  let queued = false;
  let stopped = false;
  const changes = ["friend_request_received", "friend_added", "friend_removed"];

  async function sync() {
    if (stopped || !socket.connected) return;
    if (loading) { queued = true; return; }
    loading = true;
    const started = revision;
    try {
      const [first, incoming, outgoing] = await Promise.all([
        api("/friends?page_size=100", {authenticated: true}),
        api("/friends/requests?direction=incoming", {authenticated: true}),
        api("/friends/requests?direction=outgoing", {authenticated: true}),
      ]);
      const friends = [...first.items];
      for (let page = 2; friends.length < first.total; page++) {
        const next = await api(`/friends?page_size=100&page=${page}`, {authenticated: true});
        friends.push(...next.items);
        if (!next.items.length || started !== revision || !socket.connected || stopped) break;
      }
      if (!stopped && socket.connected && started === revision) {
        window.dispatchEvent(new CustomEvent("videocall:friends-synced", {
          detail: {friends, incoming: incoming.items, outgoing: outgoing.items},
        }));
      }
    } catch (error) {
      if (!stopped && socket.connected && started === revision) {
        window.dispatchEvent(new CustomEvent("videocall:friends-sync-error", {
          detail: {code: error.code || "NETWORK_ERROR"},
        }));
      }
    } finally {
      loading = false;
      if (queued) { queued = false; sync(); }
    }
  }

  function refresh() { revision++; sync(); }
  function disconnected() { revision++; }
  socket.on("connect", refresh);
  socket.on("disconnect", disconnected);
  for (const event of changes) socket.on(event, refresh);
  if (socket.connected) refresh();
  return () => {
    stopped = true;
    revision++;
    socket.off("connect", refresh);
    socket.off("disconnect", disconnected);
    for (const event of changes) socket.off(event, refresh);
  };
}
