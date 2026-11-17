import * as SecureStore from "expo-secure-store";

declare const process: {env: {EXPO_PUBLIC_API_URL?: string}};

const refreshKey = "videocall.refresh";
export const origin = (process.env.EXPO_PUBLIC_API_URL || "").trim().replace(/\/+$/, "");

export interface PublicConfig {
  project_name?: string;
  brand_color?: string;
  brand_font?: "system" | "serif" | "monospace";
  allow_registration: boolean;
  maintenance_mode: boolean;
  maintenance_message: string;
  meeting_enabled?: boolean;
  livestream_enabled?: boolean;
}

export interface Profile {
  display_name: string;
  must_change_password: boolean;
}

interface Tokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

interface Session extends Tokens {
  expiresAt: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details: Record<string, string> = {},
  ) {
    super(message);
  }
}

let session: Session | undefined;
let rotating: Promise<string> | undefined;
let revision = 0;
let storageWork = Promise.resolve();

function persist(work: () => Promise<void>) {
  const result = storageWork.then(work);
  storageWork = result.catch(() => {});
  return result;
}

async function request<T>(path: string, method: string, body?: unknown, token?: string): Promise<T> {
  if (!origin) throw new Error("Hãy đặt địa chỉ máy chủ Videocall trong tệp .env của app.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(origin + "/api/v1" + path, {
      method,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? {"Content-Type": "application/json"} : {}),
        ...(token ? {Authorization: "Bearer " + token} : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(
        data?.error?.message || "Máy chủ chưa xử lý được yêu cầu.",
        response.status, data?.error?.code, data?.error?.details,
      );
    }
    return data as T;
  } finally {
    clearTimeout(timeout);
  }
}

async function save(tokens: Tokens, started = revision) {
  await persist(async () => {
    if (revision !== started) throw new Error("Phiên đăng nhập đã thay đổi.");
    await SecureStore.setItemAsync(refreshKey, tokens.refresh_token);
  });
  if (revision !== started) return;
  session = {...tokens, expiresAt: Date.now() + tokens.expires_in * 1000};
}

export async function clearSession() {
  revision++;
  session = undefined;
  await persist(() => SecureStore.deleteItemAsync(refreshKey));
}

export async function accessToken(force = false): Promise<string> {
  if (!force && session && session.expiresAt > Date.now() + 5000) return session.access_token;
  if (!rotating) {
    const started = revision;
    rotating = (async () => {
      const refresh = session?.refresh_token ?? await SecureStore.getItemAsync(refreshKey);
      if (!refresh) throw new ApiError("Bạn cần đăng nhập.", 401, "UNAUTHENTICATED");
      const tokens = await request<Tokens>("/auth/refresh", "POST", {refresh_token: refresh});
      await save(tokens, started);
      if (revision !== started) throw new ApiError("Phiên đã kết thúc.", 401, "UNAUTHENTICATED");
      return tokens.access_token;
    })().catch(async error => {
      if (started === revision && error instanceof ApiError && [401, 403].includes(error.status)) {
        await clearSession();
      }
      throw error;
    }).finally(() => { rotating = undefined; });
  }
  return rotating;
}

export async function api<T>(
  path: string, {method = "GET", body, authenticated = false}: {
    method?: string; body?: unknown; authenticated?: boolean;
  } = {},
): Promise<T> {
  if (!authenticated) return request<T>(path, method, body);
  try {
    return await request<T>(path, method, body, await accessToken());
  } catch (error) {
    if (error instanceof ApiError && error.code === "TOKEN_EXPIRED") {
      return request<T>(path, method, body, await accessToken(true));
    }
    throw error;
  }
}

export async function signIn(email: string, password: string) {
  await save(await request<Tokens>("/auth/login", "POST", {email, password}));
}

export async function transfer(transferToken: string, action: "confirm" | "cancel") {
  const tokens = await request<Tokens | null>(
    "/auth/device-transfer/" + action, "POST", {transfer_token: transferToken},
  );
  if (tokens) await save(tokens);
}

export async function logout() {
  const refresh = session?.refresh_token ?? await SecureStore.getItemAsync(refreshKey);
  try {
    if (refresh) await request("/auth/logout", "POST", {refresh_token: refresh});
  } finally {
    await clearSession();
  }
}
