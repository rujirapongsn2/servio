"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, ImagePlus, Loader2, Palette, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAdminLocale } from "@/lib/admin-locale";
import { DEFAULT_GREETING, themeAssetUrl, type ChatLocale, type ChatPalette, type ChatTheme } from "@/lib/chat-theme";
import {
  deleteWidgetLogo, getWidgetTheme, previewWidgetPalette, resetWidgetTheme, saveWidgetTheme, uploadWidgetLogo,
  type AdminChatTheme, type ThemeUpdate,
} from "@/lib/widgetTheme";

const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const PREVIEW = "servio.theme.preview";

const COPY = {
  th: {
    title: "ธีมของแชต", intro: "ปรับสี โลโก้ และคำทักทายให้เข้ากับแบรนด์ ใช้กับปุ่มแชตบนเว็บไซต์และลิงก์แชตโดยตรงของคีย์นี้",
    color: "สีหลัก", colorHint: "ใช้กับปุ่ม ฟองข้อความของลูกค้า และพื้นหลังโทนอ่อน", custom: "รหัสสี", invalidHex: "ใส่รหัสสีแบบ #RRGGBB",
    textOnColor: "ตัวอักษรบนสีนี้", white: "สีขาว", dark: "สีเข้ม", passes: "อ่านง่ายตามมาตรฐาน AA",
    logo: "โลโก้", logoHint: "PNG, JPG หรือ WebP ไม่เกิน 512 KB ไม่รับ SVG แนะนำภาพแนวนอนพื้นโปร่งใส", upload: "อัปโหลดโลโก้", replace: "เปลี่ยนโลโก้",
    removeLogo: "ลบโลโก้", noLogo: "ยังไม่มีโลโก้ ใช้โลโก้ Servio", launcherLogo: "แสดงโลโก้บนปุ่มแชต", launcherLogoHint: "เหมาะกับโลโก้ที่เป็นสัญลักษณ์ ถ้าเป็นตัวอักษรยาวให้ใช้ไอคอนเดิม",
    logoSavedNow: "โลโก้บันทึกทันทีเมื่ออัปโหลดหรือลบ",
    greeting: "คำทักทาย", greetingTitle: "หัวข้อ", greetingSubtitle: "ข้อความรอง", greetingHint: "เว้นว่างไว้เพื่อใช้ข้อความเริ่มต้น",
    th: "ไทย", en: "English",
    preview: "ตัวอย่าง", sampleWelcome: "หน้าต้อนรับ", sampleConversation: "บทสนทนา", previewNote: "ตัวอย่างนี้คือหน้าแชตจริงที่ลูกค้าจะเห็น",
    save: "บันทึกธีม", saving: "กำลังบันทึก…", saved: "บันทึกแล้ว", unsaved: "มีการเปลี่ยนแปลงที่ยังไม่บันทึก", upToDate: "ธีมเป็นปัจจุบัน",
    reset: "คืนค่าเริ่มต้น", confirmReset: "ยืนยันคืนค่า (ลบโลโก้ด้วย)", cancel: "ยกเลิก", resetDone: "คืนค่าธีม Servio แล้ว",
    loading: "กำลังโหลดธีม…", loadFailed: "โหลดธีมไม่สำเร็จ", retry: "ลองอีกครั้ง",
    presets: { servio: "Servio", emerald: "มรกต", indigo: "คราม", coral: "ปะการัง", graphite: "กราไฟต์" } as Record<string, string>,
  },
  en: {
    title: "Chat theme", intro: "Match the colour, logo and greeting to your brand. Applies to the website chat button and the direct chat link for this key.",
    color: "Primary colour", colorHint: "Used for buttons, customer bubbles and the soft background", custom: "Hex code", invalidHex: "Enter a colour as #RRGGBB",
    textOnColor: "Text on this colour", white: "White", dark: "Dark", passes: "Meets WCAG AA",
    logo: "Logo", logoHint: "PNG, JPG or WebP up to 512 KB. SVG is not accepted. A wide logo on a transparent background works best.", upload: "Upload logo", replace: "Replace logo",
    removeLogo: "Remove logo", noLogo: "No logo yet, the Servio logo is shown", launcherLogo: "Show the logo on the chat button", launcherLogoHint: "Best for symbol logos. Keep the icon for long wordmarks.",
    logoSavedNow: "Logo changes are saved immediately",
    greeting: "Greeting", greetingTitle: "Heading", greetingSubtitle: "Supporting text", greetingHint: "Leave empty to use the default text",
    th: "ไทย", en: "English",
    preview: "Preview", sampleWelcome: "Welcome", sampleConversation: "Conversation", previewNote: "This is the real chat your customers will see",
    save: "Save theme", saving: "Saving…", saved: "Saved", unsaved: "You have unsaved changes", upToDate: "Theme is up to date",
    reset: "Restore default", confirmReset: "Confirm restore (removes the logo)", cancel: "Cancel", resetDone: "Servio theme restored",
    loading: "Loading theme…", loadFailed: "Couldn't load the theme", retry: "Try again",
    presets: { servio: "Servio", emerald: "Emerald", indigo: "Indigo", coral: "Coral", graphite: "Graphite" } as Record<string, string>,
  },
};

type Draft = { primary: string; greeting: Record<ChatLocale, { title: string; subtitle: string }>; launcherLogo: boolean };

function draftFrom(theme: AdminChatTheme): Draft {
  return {
    primary: theme.primary_color,
    greeting: {
      th: { title: theme.greeting.th?.title ?? "", subtitle: theme.greeting.th?.subtitle ?? "" },
      en: { title: theme.greeting.en?.title ?? "", subtitle: theme.greeting.en?.subtitle ?? "" },
    },
    launcherLogo: theme.launcher_logo,
  };
}

function normalizeHex(value: string) {
  const v = value.trim().toLowerCase();
  return v.length === 4 ? `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}` : v;
}

export default function WidgetThemeEditor({ token, keyId }: { token: string; keyId: number }) {
  const { locale: adminLocale } = useAdminLocale();
  const t = COPY[adminLocale];
  const [saved, setSaved] = useState<AdminChatTheme | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [hexInput, setHexInput] = useState("");
  const [palette, setPalette] = useState<{ palette: ChatPalette; warnings: string[] } | null>(null);
  const [greetingLocale, setGreetingLocale] = useState<ChatLocale>("th");
  const [sample, setSample] = useState<"welcome" | "conversation">("welcome");
  const [status, setStatus] = useState<{ kind: "idle" | "loading" | "saving" | "saved" | "error"; message?: string }>({ kind: "loading" });
  const [busyLogo, setBusyLogo] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const adopt = useCallback((theme: AdminChatTheme) => {
    setSaved(theme);
    setDraft(draftFrom(theme));
    setHexInput(theme.primary_color);
    setPalette({ palette: theme.palette, warnings: theme.warnings });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setStatus({ kind: "loading" });
    getWidgetTheme(token, keyId)
      .then((theme) => { if (!cancelled) { adopt(theme); setStatus({ kind: "idle" }); } })
      .catch((error: Error) => { if (!cancelled) setStatus({ kind: "error", message: `${t.loadFailed}: ${error.message}` }); });
    return () => { cancelled = true; };
  }, [token, keyId, adopt, loadAttempt, t.loadFailed]);

  // Palette comes from the server so the preview matches the live widget exactly.
  useEffect(() => {
    if (!draft || !HEX.test(draft.primary)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      previewWidgetPalette(token, draft.primary, controller.signal).then(setPalette).catch(() => {});
    }, 120);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [token, draft?.primary]); // eslint-disable-line react-hooks/exhaustive-deps

  const previewTheme: ChatTheme | null = useMemo(() => {
    if (!saved || !draft || !palette) return null;
    const greeting: ChatTheme["greeting"] = {};
    for (const locale of ["th", "en"] as const) {
      const entry = draft.greeting[locale];
      greeting[locale] = { ...(entry.title.trim() ? { title: entry.title.trim() } : {}), ...(entry.subtitle.trim() ? { subtitle: entry.subtitle.trim() } : {}) };
    }
    return { ...saved, primary_color: draft.primary, palette: palette.palette, greeting, launcher_logo: draft.launcherLogo && Boolean(saved.logo_url) };
  }, [saved, draft, palette]);

  const postPreview = useCallback(() => {
    const target = frame.current?.contentWindow;
    if (!target || !previewTheme) return;
    target.postMessage({ type: PREVIEW, theme: previewTheme, sample, mode: "chat" }, window.location.origin);
  }, [previewTheme, sample]);

  useEffect(() => { postPreview(); }, [postPreview]);
  useEffect(() => {
    const ready = (event: MessageEvent) => {
      if (event.origin === window.location.origin && event.source === frame.current?.contentWindow && event.data?.type === `${PREVIEW}.ready`) postPreview();
    };
    window.addEventListener("message", ready);
    return () => window.removeEventListener("message", ready);
  }, [postPreview]);

  if (status.kind === "loading" && !draft) {
    return <section className="rounded-lg border border-[#E2E8F0] bg-white p-5 text-sm text-[#526277]" aria-busy="true"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden="true" />{t.loading}</section>;
  }
  if (!draft || !saved) {
    return (
      <section className="rounded-lg border border-[#F3C9C3] bg-[#FFF7F5] p-5 text-sm text-[#7A271A]" role="alert">
        <p className="m-0 font-medium">{status.message ?? t.loadFailed}</p>
        <Button className="mt-3" size="sm" variant="outline" onClick={() => setLoadAttempt((n) => n + 1)}>{t.retry}</Button>
      </section>
    );
  }

  const savedDraft = draftFrom(saved);
  const dirty = JSON.stringify(savedDraft) !== JSON.stringify(draft);
  const hexValid = HEX.test(hexInput.trim());
  const textColor = palette?.palette.on_bubble === "#ffffff" ? t.white : t.dark;
  const limits = saved.limits;
  const busy = status.kind === "saving" || busyLogo;

  const setPrimary = (value: string) => {
    setHexInput(value);
    if (HEX.test(value.trim())) setDraft((d) => d && { ...d, primary: normalizeHex(value) });
  };
  const setGreeting = (field: "title" | "subtitle", value: string) =>
    setDraft((d) => d && { ...d, greeting: { ...d.greeting, [greetingLocale]: { ...d.greeting[greetingLocale], [field]: value } } });

  const save = async () => {
    setStatus({ kind: "saving" });
    const update: ThemeUpdate = { primary_color: draft.primary, greeting: draft.greeting, launcher_logo: draft.launcherLogo };
    try { adopt(await saveWidgetTheme(token, keyId, update)); setStatus({ kind: "saved", message: t.saved }); }
    catch (error) { setStatus({ kind: "error", message: (error as Error).message }); }
  };
  const reset = async () => {
    setConfirmReset(false);
    setStatus({ kind: "saving" });
    try { adopt(await resetWidgetTheme(token, keyId)); setStatus({ kind: "saved", message: t.resetDone }); }
    catch (error) { setStatus({ kind: "error", message: (error as Error).message }); }
  };
  const logoAction = async (action: () => Promise<AdminChatTheme>) => {
    setBusyLogo(true);
    try {
      const theme = await action();
      // Keep unsaved colour/greeting edits; only the logo changed on the server.
      setSaved(theme);
      setDraft((d) => d && { ...d, launcherLogo: d.launcherLogo && Boolean(theme.logo_url) });
      setStatus({ kind: "idle" });
    } catch (error) { setStatus({ kind: "error", message: (error as Error).message }); }
    finally { setBusyLogo(false); }
  };
  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (!limits.logo_types.includes(file.type)) { setStatus({ kind: "error", message: adminLocale === "th" ? "รองรับเฉพาะ PNG, JPG หรือ WebP (ไม่รับ SVG)" : "Only PNG, JPG or WebP (no SVG)" }); return; }
    if (file.size > limits.logo_bytes) { setStatus({ kind: "error", message: adminLocale === "th" ? "โลโก้ต้องมีขนาดไม่เกิน 512 KB" : "The logo must be 512 KB or smaller" }); return; }
    void logoAction(() => uploadWidgetLogo(token, keyId, file));
  };

  const greetingDraft = draft.greeting[greetingLocale];
  const placeholder = DEFAULT_GREETING[greetingLocale];
  const statusLine = status.kind === "saving" ? t.saving : status.kind === "error" ? status.message : status.kind === "saved" && !dirty ? status.message : dirty ? t.unsaved : t.upToDate;
  const launcherBg = palette ? `linear-gradient(145deg, ${palette.palette.primary}, ${palette.palette.primary_strong})` : undefined;
  const logoSrc = themeAssetUrl(saved.logo_url);

  return (
    <section className="rounded-lg border border-[#E2E8F0] bg-white" aria-labelledby="widget-theme-title">
      <div className="border-b border-[#E2E8F0] px-5 py-4">
        <h3 id="widget-theme-title" className="flex items-center gap-2 text-base font-semibold text-[#0D1B2A]"><Palette className="h-4 w-4 text-[#2786C2]" aria-hidden="true" />{t.title}</h3>
        <p className="mt-1 text-sm text-[#526277]">{t.intro}</p>
      </div>

      <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0 space-y-6">
          <fieldset>
            <legend className="text-sm font-semibold text-[#0D1B2A]">{t.color}</legend>
            <p className="mt-1 text-xs text-[#526277]">{t.colorHint}</p>
            <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label={t.color}>
              {saved.presets.map((preset) => {
                const active = draft.primary === preset.primary;
                return (
                  <button key={preset.id} type="button" role="radio" aria-checked={active} onClick={() => setPrimary(preset.primary)}
                    className={`inline-flex min-h-[40px] items-center gap-2 rounded-full border py-1.5 pl-1.5 pr-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1A5A8A] ${active ? "border-[#0D1B2A] bg-[#F8FAFC] text-[#0D1B2A]" : "border-[#E2E8F0] text-[#2D3F55] hover:border-[#CBD5E1]"}`}>
                    <span className="grid h-7 w-7 place-items-center rounded-full" style={{ background: preset.primary }} aria-hidden="true">{active && <Check className="h-4 w-4 text-white" />}</span>
                    {t.presets[preset.id] ?? preset.id}
                  </button>
                );
              })}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <label className="inline-flex items-center gap-2 text-sm text-[#2D3F55]">
                <input type="color" value={HEX.test(draft.primary) ? normalizeHex(draft.primary) : "#2786c2"} onChange={(e) => setPrimary(e.target.value)}
                  className="h-10 w-12 cursor-pointer rounded-md border border-[#E2E8F0] bg-white p-1" aria-label={t.color} />
              </label>
              <label className="flex flex-col text-xs font-medium text-[#2D3F55]">
                <span className="sr-only">{t.custom}</span>
                <input type="text" inputMode="text" spellCheck={false} maxLength={7} value={hexInput} onChange={(e) => setPrimary(e.target.value)}
                  aria-invalid={!hexValid} aria-describedby="theme-hex-hint"
                  className={`h-10 w-28 rounded-md border px-3 font-mono text-sm text-[#0D1B2A] outline-none focus:ring-2 focus:ring-[#2786C2] ${hexValid ? "border-[#E2E8F0]" : "border-[#D92D20]"}`} />
              </label>
              <span id="theme-hex-hint" className={`text-xs ${hexValid ? "text-[#526277]" : "text-[#B42318]"}`}>
                {hexValid ? <>{t.textOnColor}: <strong className="font-semibold text-[#0D1B2A]">{textColor}</strong> · {t.passes}</> : t.invalidHex}
              </span>
            </div>
            {palette && palette.warnings.length > 0 && (
              <ul className="mt-3 space-y-1 rounded-md border border-[#FEDF89] bg-[#FFFAEB] px-3 py-2 text-xs text-[#93370D]" aria-live="polite">
                {palette.warnings.map((warning) => <li key={warning} className="flex gap-2"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />{warning}</li>)}
              </ul>
            )}
          </fieldset>

          <fieldset>
            <legend className="text-sm font-semibold text-[#0D1B2A]">{t.logo}</legend>
            <p className="mt-1 text-xs text-[#526277]">{t.logoHint}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="grid h-16 w-40 place-items-center rounded-md border border-dashed border-[#CBD5E1] bg-[#F8FAFC] px-3">
                {/* eslint-disable-next-line @next/next/no-img-element -- admin preview of an API asset */}
                {logoSrc ? <img src={logoSrc} alt={t.logo} className="max-h-12 max-w-full object-contain" />
                  : <span className="text-center text-xs text-[#526277]">{t.noLogo}</span>}
              </div>
              <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} aria-hidden="true"
                onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
              <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => fileInput.current?.click()}>
                {busyLogo ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ImagePlus className="h-4 w-4" aria-hidden="true" />}
                {saved.logo_url ? t.replace : t.upload}
              </Button>
              {saved.logo_url && (
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => void logoAction(() => deleteWidgetLogo(token, keyId))}>
                  <Trash2 className="h-4 w-4" aria-hidden="true" />{t.removeLogo}
                </Button>
              )}
            </div>
            <label className={`mt-3 flex items-start gap-3 rounded-md border border-[#E2E8F0] px-3 py-2 ${saved.logo_url ? "" : "opacity-60"}`}>
              <input type="checkbox" className="mt-1 h-4 w-4 rounded border-gray-300 text-[#2786C2] focus:ring-[#2786C2]" disabled={!saved.logo_url}
                checked={draft.launcherLogo && Boolean(saved.logo_url)} onChange={(e) => setDraft((d) => d && { ...d, launcherLogo: e.target.checked })} />
              <span><span className="block text-sm font-medium text-[#2D3F55]">{t.launcherLogo}</span><span className="block text-xs text-[#526277]">{t.launcherLogoHint}</span></span>
            </label>
            <p className="mt-2 text-xs text-[#526277]">{t.logoSavedNow}</p>
          </fieldset>

          <fieldset>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <legend className="text-sm font-semibold text-[#0D1B2A]">{t.greeting}</legend>
              <div className="inline-flex rounded-md border border-[#E2E8F0] p-0.5" role="tablist" aria-label={t.greeting}>
                {(["th", "en"] as const).map((code) => (
                  <button key={code} type="button" role="tab" aria-selected={greetingLocale === code} onClick={() => setGreetingLocale(code)}
                    className={`min-h-[32px] rounded px-3 text-xs font-medium ${greetingLocale === code ? "bg-[#0D1B2A] text-white" : "text-[#2D3F55] hover:bg-[#F1F5F9]"}`}>{t[code]}</button>
                ))}
              </div>
            </div>
            <p className="mt-1 text-xs text-[#526277]">{t.greetingHint}</p>
            <div className="mt-3 space-y-3" lang={greetingLocale}>
              <label className="block">
                <span className="flex justify-between text-xs font-medium text-[#2D3F55]"><span>{t.greetingTitle}</span><span className="tabular-nums text-[#526277]">{greetingDraft.title.length}/{limits.greeting_title}</span></span>
                <input type="text" value={greetingDraft.title} maxLength={limits.greeting_title} placeholder={placeholder.title} onChange={(e) => setGreeting("title", e.target.value)}
                  className="mt-1 h-10 w-full rounded-md border border-[#E2E8F0] px-3 text-sm text-[#0D1B2A] outline-none placeholder:text-[#64748B] focus:ring-2 focus:ring-[#2786C2]" />
              </label>
              <label className="block">
                <span className="flex justify-between text-xs font-medium text-[#2D3F55]"><span>{t.greetingSubtitle}</span><span className="tabular-nums text-[#526277]">{greetingDraft.subtitle.length}/{limits.greeting_subtitle}</span></span>
                <textarea value={greetingDraft.subtitle} maxLength={limits.greeting_subtitle} rows={2} placeholder={placeholder.subtitle} onChange={(e) => setGreeting("subtitle", e.target.value)}
                  className="mt-1 w-full resize-none rounded-md border border-[#E2E8F0] px-3 py-2 text-sm text-[#0D1B2A] outline-none placeholder:text-[#64748B] focus:ring-2 focus:ring-[#2786C2]" />
              </label>
            </div>
          </fieldset>
        </div>

        <div className="min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-[#0D1B2A]">{t.preview}</h4>
            <div className="inline-flex rounded-md border border-[#E2E8F0] p-0.5" role="tablist" aria-label={t.preview}>
              {(["welcome", "conversation"] as const).map((value) => (
                <button key={value} type="button" role="tab" aria-selected={sample === value} onClick={() => setSample(value)}
                  className={`min-h-[32px] rounded px-3 text-xs font-medium ${sample === value ? "bg-[#0D1B2A] text-white" : "text-[#2D3F55] hover:bg-[#F1F5F9]"}`}>
                  {value === "welcome" ? t.sampleWelcome : t.sampleConversation}
                </button>
              ))}
            </div>
          </div>
          <div className="relative mt-3 rounded-xl bg-[#F1F5F9] p-3 pb-20">
            <iframe ref={frame} title={t.preview} src={`/widget?preview=1&type=chat&allowToggle=false&lang=${greetingLocale}`} onLoad={postPreview}
              className="block h-[520px] w-full rounded-[22px] border bg-white shadow-[0_20px_60px_-24px_rgba(13,27,42,0.35)]"
              style={{ borderColor: palette?.palette.frame_border ?? "#dce8f1" }} />
            <span className="absolute bottom-4 right-4 grid h-14 w-14 place-items-center rounded-full border shadow-[0_8px_24px_rgba(13,27,42,0.2)]" aria-hidden="true"
              style={draft.launcherLogo && logoSrc ? { background: "#fff", borderColor: palette?.palette.frame_border } : { background: launcherBg, color: palette?.palette.on_primary, borderColor: "rgba(255,255,255,.65)" }}>
              {draft.launcherLogo && logoSrc
                // eslint-disable-next-line @next/next/no-img-element -- launcher preview
                ? <img src={logoSrc} alt="" className="max-h-[38px] max-w-[38px] object-contain" />
                : <svg viewBox="0 0 24 24" width="25" height="25" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" /><path d="M8 10h8M8 14h5" /></svg>}
            </span>
          </div>
          <p className="mt-2 text-xs text-[#526277]">{t.previewNote}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E2E8F0] px-5 py-4">
        <p className={`m-0 flex items-center gap-2 text-sm ${status.kind === "error" ? "text-[#B42318]" : "text-[#526277]"}`} role="status" aria-live="polite">
          {status.kind === "saving" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {status.kind === "saved" && !dirty && <Check className="h-4 w-4 text-[#067647]" aria-hidden="true" />}
          {status.kind === "error" && <AlertTriangle className="h-4 w-4" aria-hidden="true" />}
          {statusLine}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {confirmReset ? (
            <>
              <Button type="button" size="sm" variant="outline" onClick={() => setConfirmReset(false)}>{t.cancel}</Button>
              <Button type="button" size="sm" variant="stop" disabled={busy} onClick={() => void reset()}>{t.confirmReset}</Button>
            </>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={busy || saved.is_default} onClick={() => setConfirmReset(true)}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />{t.reset}
            </Button>
          )}
          <Button type="button" size="sm" disabled={!dirty || !hexValid || busy} onClick={() => void save()}>
            {status.kind === "saving" ? t.saving : t.save}
          </Button>
        </div>
      </div>
    </section>
  );
}
