const STORAGE_KEY = "videocall.session";
let refreshing;

class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export function session() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(data) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
    ...session(),
    ...data,
    expiresAt: Date.now() + data.expires_in * 1000,
  }));
}

export function clearSession() {
  sessionStorage.removeItem(STORAGE_KEY);
}

export function requireSession() {
  if (!session()) {
    location.replace("/");
    return false;
  }
  return true;
}

async function request(path, method, body, token) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = "Bearer " + token;
  const response = await fetch("/api/v1" + path, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(data?.error?.message || "Yêu cầu thất bại.", data?.error?.code, response.status);
  }
  return data;
}

export async function accessToken(force = false) {
  const current = session();
  if (current && !force && current.expiresAt > Date.now() + 5000) return current.access_token;
  if (!current?.refresh_token) {
    clearSession();
    throw new ApiError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", "TOKEN_EXPIRED", 401);
  }

  if (!refreshing) {
    refreshing = request("/auth/refresh", "POST", {refresh_token: current.refresh_token})
      .then(data => {
        if (session()?.refresh_token !== current.refresh_token) {
          throw new ApiError("Phiên đăng nhập đã kết thúc.", "TOKEN_EXPIRED", 401);
        }
        saveSession(data);
        return data.access_token;
      })
      .catch(error => {
        if ([401, 403].includes(error.status) && session()?.refresh_token === current.refresh_token) {
          clearSession();
        }
        throw error;
      })
      .finally(() => { refreshing = undefined; });
  }
  return refreshing;
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
  const current = session();
  clearSession();
  if (current?.refresh_token) {
    await request("/auth/logout", "POST", {refresh_token: current.refresh_token});
  }
}
