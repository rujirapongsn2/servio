import { buildApiUrl } from "./api";
import { parseChatTheme, type ChatLocale, type ChatPalette, type ChatTheme } from "./chat-theme";

export type AdminChatTheme = ChatTheme & {
  warnings: string[];
  presets: { id: string; primary: string }[];
  limits: { greeting_title: number; greeting_subtitle: number; logo_bytes: number; logo_types: string[] };
};

export type ThemeUpdate = {
  primary_color: string | null;
  greeting: Partial<Record<ChatLocale, { title?: string; subtitle?: string }>>;
  launcher_logo: boolean;
};

async function request<T>(token: string, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(", ") : "";
    } catch { /* not JSON */ }
    if (response.status === 403) detail ||= "คุณไม่มีสิทธิ์แก้ไขธีมของคีย์นี้";
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function toAdminTheme(value: unknown): AdminChatTheme {
  const base = parseChatTheme(value);
  if (!base) throw new Error("ข้อมูลธีมไม่ถูกต้อง");
  const raw = value as Partial<AdminChatTheme>;
  return { ...base, warnings: raw.warnings ?? [], presets: raw.presets ?? [], limits: raw.limits ?? { greeting_title: 80, greeting_subtitle: 140, logo_bytes: 524288, logo_types: ["image/png", "image/jpeg", "image/webp"] } };
}

export const getWidgetTheme = (token: string, keyId: number) =>
  request<unknown>(token, `/api/admin/api-keys/${keyId}/theme`).then(toAdminTheme);

export const saveWidgetTheme = (token: string, keyId: number, update: ThemeUpdate) =>
  request<unknown>(token, `/api/admin/api-keys/${keyId}/theme`, { method: "PUT", body: JSON.stringify(update) }).then(toAdminTheme);

export const resetWidgetTheme = (token: string, keyId: number) =>
  request<unknown>(token, `/api/admin/api-keys/${keyId}/theme`, { method: "DELETE" }).then(toAdminTheme);

export function uploadWidgetLogo(token: string, keyId: number, file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<unknown>(token, `/api/admin/api-keys/${keyId}/theme/logo`, { method: "POST", body }).then(toAdminTheme);
}

export const deleteWidgetLogo = (token: string, keyId: number) =>
  request<unknown>(token, `/api/admin/api-keys/${keyId}/theme/logo`, { method: "DELETE" }).then(toAdminTheme);

export const previewWidgetPalette = (token: string, primary: string, signal?: AbortSignal) =>
  request<{ palette: ChatPalette; warnings: string[] }>(token, "/api/admin/widget-theme/preview", {
    method: "POST", body: JSON.stringify({ primary_color: primary }), signal,
  });
