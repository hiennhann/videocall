import { api } from "./api.js";

// Snapshot HTTP bù các thông báo best-effort bị mất khi socket ngắt kết nối.
export function bindFriendsSync(socket) {
  let revision = 0;
  let loading = false;
  let queued = false;
  let stopped = false;
  const changes = ["friend_request_received", "friend_added", "friend_removed", "presence_changed", "friend_profile_changed"];
  const communicationChanges = ["call_invite", "call_invite_cancelled", "call_invite_responded", "dm_message", "dm_read"];
  let communicationsRevision = 0;
  let communicationsRefresh;
  const lastSeen = new Map();

  async function syncCommunications() {
    const started = ++communicationsRevision;
    const current = () => !stopped && socket.connected && started === communicationsRevision;
    try {
      const [first, invites] = await Promise.all([
        api("/conversations?page_size=100", {authenticated: true}),
        api("/invites", {authenticated: true}),
      ]);
      const conversations = [...first.items];
      for (let page = 2; current() && conversations.length < first.total; page++) {
        const next = await api(`/conversations?page_size=100&page=${page}`, {authenticated: true});
        if (!next.items.length) break;
        conversations.push(...next.items);
      }
      const recovered = [];
      for (const conversation of conversations) {
        if (!current()) return;
        const seen = lastSeen.get(conversation.id);
        const latest = conversation.last_message?.id;
        if (seen === undefined || latest === undefined || latest <= seen) continue;
        let after = seen;
        while (current() && after < latest) {
          const batch = await api(`/conversations/${conversation.id}/messages?after=${after}&limit=100`, {authenticated: true});
          for (const message of batch.items) recovered.push({conversation_id: conversation.id, message});
          if (batch.next_after == null) break;
          after = batch.next_after;
        }
      }
      if (current()) {
        for (const conversation of conversations) {
          remember({conversation_id: conversation.id, message: conversation.last_message});
        }
        window.dispatchEvent(new CustomEvent("videocall:communications-synced", {
          detail: {conversations, invites: invites.items, recovered},
        }));
      }
    } catch (error) {
      if (current()) window.dispatchEvent(new CustomEvent("videocall:communications-sync-error", {
        detail: {code: error.code || "NETWORK_ERROR"},
      }));
    }
  }

  function remember({conversation_id, message}) {
    if (message) lastSeen.set(conversation_id, Math.max(lastSeen.get(conversation_id) ?? 0, message.id));
  }

  function refreshCommunications() {
    clearTimeout(communicationsRefresh);
    communicationsRefresh = setTimeout(() => {
      if (!stopped && socket.connected) syncCommunications();
    }, 200);
  }

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
  function connected() { refresh(); syncCommunications(); }
  function disconnected() { revision++; communicationsRevision++; }
  socket.on("connect", connected);
  socket.on("disconnect", disconnected);
  socket.on("dm_message", remember);
  for (const event of communicationChanges) socket.on(event, refreshCommunications);
  for (const event of changes) socket.on(event, refresh);
  if (socket.connected) connected();
  return () => {
    stopped = true;
    revision++;
    communicationsRevision++;
    clearTimeout(communicationsRefresh);
    lastSeen.clear();
    socket.off("connect", connected);
    socket.off("disconnect", disconnected);
    socket.off("dm_message", remember);
    for (const event of communicationChanges) socket.off(event, refreshCommunications);
    for (const event of changes) socket.off(event, refresh);
  };
}
