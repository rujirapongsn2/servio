import type { CSSProperties } from "react";
import { buildApiUrl } from "@/lib/api";

/** Derived on the server (app/widget_theme.py) so every surface shares one palette. */
export type ChatPalette = {
  primary: string;
  primary_strong: string;
  on_primary: string;
  accent_text: string;
  bubble_from: string;
  bubble_to: string;
  on_bubble: string;
  tint_1: string;
  tint_2: string;
  tint_3: string;
  base_1: string;
  base_2: string;
  base_3: string;
  frame_border: string;
  frame_bg: string;
};

export type ChatLocale = "th" | "en";
export type ChatGreeting = { title?: string; subtitle?: string };

export type ChatTheme = {
  version: number;
  is_default: boolean;
  primary_color: string;
  palette: ChatPalette;
  logo_url: string | null;
  launcher_logo: boolean;
  greeting: Partial<Record<ChatLocale, ChatGreeting>>;
};

export const DEFAULT_GREETING: Record<ChatLocale, Required<ChatGreeting>> = {
  th: { title: "สวัสดีค่ะ ให้เราช่วยอะไรดีคะ", subtitle: "สอบถามข้อมูลหรือบริการได้เลย" },
  en: { title: "Hi there, how can we help?", subtitle: "Ask us anything about our products or services." },
};

const HEX = /^#[0-9a-f]{6}$/i;
const PALETTE_KEYS: (keyof ChatPalette)[] = [
  "primary", "primary_strong", "on_primary", "accent_text", "bubble_from", "bubble_to", "on_bubble",
  "tint_1", "tint_2", "tint_3", "base_1", "base_2", "base_3", "frame_border", "frame_bg",
];

/** Accept only well-formed theme data; anything else falls back to the CSS defaults. */
export function parseChatTheme(value: unknown): ChatTheme | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const palette = raw.palette as Record<string, unknown> | undefined;
  if (!palette || !PALETTE_KEYS.every((key) => typeof palette[key] === "string" && HEX.test(palette[key] as string))) return null;
  const logo = typeof raw.logo_url === "string" && /^\/api\/public\/widget-logo\/[A-Za-z0-9_-]+\.png$/.test(raw.logo_url) ? raw.logo_url : null;
  const greeting: ChatTheme["greeting"] = {};
  const source = (raw.greeting ?? {}) as Record<string, unknown>;
  for (const locale of ["th", "en"] as const) {
    const entry = source[locale] as Record<string, unknown> | undefined;
    if (!entry) continue;
    greeting[locale] = {
      ...(typeof entry.title === "string" && entry.title ? { title: entry.title.slice(0, 80) } : {}),
      ...(typeof entry.subtitle === "string" && entry.subtitle ? { subtitle: entry.subtitle.slice(0, 140) } : {}),
    };
  }
  return {
    version: Number(raw.version) || 1,
    is_default: raw.is_default === true,
    primary_color: typeof raw.primary_color === "string" ? raw.primary_color : palette.primary as string,
    palette: Object.fromEntries(PALETTE_KEYS.map((key) => [key, palette[key]])) as ChatPalette,
    logo_url: logo,
    launcher_logo: raw.launcher_logo === true && Boolean(logo),
    greeting,
  };
}

/** CSS custom properties consumed by ChatSurface.module.css. */
export function chatThemeStyle(theme: ChatTheme | null | undefined): CSSProperties | undefined {
  if (!theme) return undefined;
  const p = theme.palette;
  return {
    "--chat-primary": p.primary,
    "--chat-hover": p.primary_strong,
    "--chat-on-primary": p.on_primary,
    "--chat-accent": p.accent_text,
    "--chat-bubble-from": p.bubble_from,
    "--chat-bubble-to": p.bubble_to,
    "--chat-on-bubble": p.on_bubble,
    "--chat-submit-bg": `linear-gradient(145deg, ${p.primary}, ${p.primary_strong})`,
    "--chat-tint-1": p.tint_1,
    "--chat-tint-2": p.tint_2,
    "--chat-tint-3": p.tint_3,
    "--chat-base-1": p.base_1,
    "--chat-base-2": p.base_2,
    "--chat-base-3": p.base_3,
  } as CSSProperties;
}

export function resolveGreeting(theme: ChatTheme | null | undefined, locale: ChatLocale): Required<ChatGreeting> {
  const custom = theme?.greeting?.[locale];
  return {
    title: custom?.title || DEFAULT_GREETING[locale].title,
    subtitle: custom?.subtitle || DEFAULT_GREETING[locale].subtitle,
  };
}

export function themeAssetUrl(path: string | null | undefined): string | null {
  return path ? buildApiUrl(path) : null;
}

export async function fetchPublicChatTheme(apiKey: string, signal?: AbortSignal): Promise<ChatTheme | null> {
  if (!apiKey) return null;
  const response = await fetch(buildApiUrl(`/api/public/widget-theme?api_key=${encodeURIComponent(apiKey)}`), { signal });
  if (!response.ok) return null;
  return parseChatTheme(await response.json());
}
