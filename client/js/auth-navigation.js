const pages = new Set(["/lobby", "/rooms", "/account", "/rooms/join", "/rooms/create", "/room"]);

export function loginDestination(value) {
  if (!value) return "/lobby";
  try {
    const url = new URL(value, location.origin);
    if (url.origin === location.origin && pages.has(url.pathname)) {
      return url.pathname + url.search + url.hash;
    }
  } catch { /* An invalid destination returns to the home page. */ }
  return "/lobby";
}

export function loginUrl() {
  const next = loginDestination(location.pathname + location.search + location.hash);
  return "/?" + new URLSearchParams({next});
}
