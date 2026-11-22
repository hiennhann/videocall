import { loginUrl } from "./auth-navigation.js";

const STORAGE_KEY = "videocall.session";
const NOTICE_KEY = "videocall.login-notice";
const sessionChannel = typeof BroadcastChannel === "function" ? new BroadcastChannel("videocall-auth") : null;
let accountSession;
let refreshing;
let revision = 0;

class ApiError extends Error {
  constructor(message, code, status, details) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function session() {
  if (accountSession) return accountSession;
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const stored = JSON.parse(raw);
    return stored?.user?.role === "guest" ? stored : null;
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(data) {
  const value = {
    ...session(),
    ...data,
    expiresAt: Date.now() + data.expires_in * 1000,
  };
  if (data.user?.role === "guest") {
    accountSession = undefined;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } else {
    sessionStorage.removeItem(STORAGE_KEY);
    accountSession = value;
  }
}

export function clearSession() {
  revision++;
  accountSession = undefined;
  sessionStorage.removeItem(STORAGE_KEY);
}

export function sessionEnded(notice, broadcast = true) {
  const wasGuest = session()?.user?.role === "guest";
  clearSession();
  if (broadcast && !wasGuest) sessionChannel?.postMessage(notice);
  if (notice) sessionStorage.setItem(NOTICE_KEY, notice);
  if (location.pathname !== "/") location.replace("/");
}

sessionChannel?.addEventListener("message", ({data}) => {
  if (accountSession && typeof data === "string") sessionEnded(data, false);
});

export function takeSessionNotice() {
  const notice = sessionStorage.getItem(NOTICE_KEY);
  sessionStorage.removeItem(NOTICE_KEY);
  return notice;
}

export async function restoreSession() {
  try {
    await accessToken();
    return true;
  } catch {
    return false;
  }
}

export async function requireSession() {
  if (!await restoreSession()) {
    location.replace(loginUrl());
    return false;
  }
  return true;
}

async function request(path, method, body, token) {
  const headers = {};
  const multipart = body instanceof FormData;
  if (body !== undefined && !multipart) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch("/api/v1" + path, {
    method, headers, body: body === undefined || multipart ? body : JSON.stringify(body),
    cache: "no-store", keepalive: path === "/auth/refresh",
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      data?.error?.details?.notice || data?.error?.message || "Yêu cầu thất bại.",
      data?.error?.code, response.status, data?.error?.details,
    );
  }
  return data;
}

export async function accessToken(force = false) {
  const current = session();
  if (current && !force && current.expiresAt > Date.now() + 5000) return current.access_token;
  if (current?.user?.role === "guest") {
    clearSession();
    throw new ApiError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "TOKEN_EXPIRED", 401);
  }

  if (!refreshing) {
    const started = revision;
    const bootstrap = !current && !force
      ? request("/auth/session", "POST").catch(error => {
        if (error.status !== 401) throw error;
        return withSessionLock(() => request("/auth/refresh", "POST"));
      })
      : withSessionLock(() => request("/auth/refresh", "POST"));
    refreshing = bootstrap
      .then(data => {
        if (revision !== started) {
          throw new ApiError("Phiên đăng nhập đã kết thúc.", "TOKEN_EXPIRED", 401);
        }
        saveSession(data);
        return data.access_token;
      })
      .catch(error => {
        if ([401, 403].includes(error.status) && revision === started) {
          clearSession();
        }
        throw error;
      })
      .finally(() => { refreshing = undefined; });
  }
  return refreshing;
}

function withSessionLock(work) {
  return navigator.locks ? navigator.locks.request("videocall-auth", work) : work();
}

export async function api(path, {method = "GET", body, authenticated = false} = {}) {
  if (!authenticated) return request(path, method, body);
  const token = await accessToken();
  try {
    return await request(path, method, body, token);
  } catch (error) {
    if (error.code === "TOKEN_EXPIRED") {
      return request(path, method, body, await accessToken(true));
    }
    if (error.code === "ACCOUNT_DISABLED") clearSession();
    throw error;
  }
}

export async function logout() {
  try {
    await withSessionLock(() => request("/auth/logout", "POST"));
  } finally {
    sessionEnded("Bạn đã đăng xuất.");
  }
}
