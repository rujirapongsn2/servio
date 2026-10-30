"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Save, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import WidgetThemeEditor from "@/components/WidgetThemeEditor";
import { useAdminLocale } from "@/lib/admin-locale";
import { channelDate, loadChannelDraft, saveChannelDraft, type ChannelDraft, type OverviewChannel } from "@/lib/channels-overview";

const control = "mt-1.5 w-full rounded-lg border border-control bg-surface px-3 py-2 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";
const fields = {
  line: [["channel_id", "Channel ID", false], ["channel_secret", "Channel Secret", true], ["channel_access_token", "Channel Access Token", true]],
  facebook: [["page_id", "Page ID", false], ["app_id", "App ID", false], ["app_secret", "App Secret", true], ["page_access_token", "Page Access Token", true], ["verify_token", "Verify Token", true]],
} satisfies Record<"line" | "facebook", [string, string, boolean][]>;

type EditorState = { kind: "loading" } | { kind: "failed"; message: string } | { kind: "ready"; draft: ChannelDraft; saved: ChannelDraft };
export default function ChannelOverviewEditor({ row, onClose, onSaved }: { row: OverviewChannel; onClose: () => void; onSaved: () => void }) {
  const { locale } = useAdminLocale();
  const tr = (th: string, en: string) => locale === "th" ? th : en;
  const [state, setState] = useState<EditorState>({ kind: "loading" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [renewal, setRenewal] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [themeOpen, setThemeOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  const nameField = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    loadChannelDraft(row, controller.signal).then(draft => {
      if (!controller.signal.aborted) setState({ kind: "ready", draft, saved: draft });
    }).catch((e: unknown) => { if (!controller.signal.aborted) setState({ kind: "failed", message: e instanceof Error ? e.message : "Unable to load channel" }); });
    return () => controller.abort();
  }, [row, retry]);
  const ready = state.kind === "ready";
  useEffect(() => { if (ready) nameField.current?.focus(); }, [ready]);
  const dirty = state.kind === "ready" && (JSON.stringify(state.draft) !== JSON.stringify(state.saved) || Boolean(renewal));
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const close = () => { if (!saving && (!dirty || window.confirm(tr("ยกเลิกการเปลี่ยนแปลงที่ยังไม่บันทึก?", "Discard unsaved changes?")))) onClose(); };
  const patch = (change: Partial<ChannelDraft>) => setState(previous => previous.kind === "ready" ? { ...previous, draft: { ...previous.draft, ...change } } : previous);
  const copy = async (value: string) => {
    try { await navigator.clipboard.writeText(value); setCopyNotice(tr("คัดลอกแล้ว", "Copied")); }
    catch { setCopyNotice(tr("คัดลอกไม่สำเร็จ โปรดเลือกข้อความเพื่อคัดลอก", "Copy failed. Select the text to copy.")); }
  };
  if (state.kind === "loading") return <div role="status" className="p-5 text-sm text-fg-2">{tr("กำลังโหลดการตั้งค่า…", "Loading settings…")}</div>;
  if (state.kind === "failed") return <div className="space-y-3 p-5"><p role="alert" className="text-sm text-danger">{state.message}</p><Button variant="outline" onClick={() => setRetry(v => v + 1)}>{tr("ลองอีกครั้ง", "Retry")}</Button><Button variant="ghost" onClick={onClose}>{tr("ปิด", "Close")}</Button></div>;
  const { draft } = state;
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const chatLink = row.kind === "web" && row.slug ? `${origin}/c/${row.slug}?type=chat` : "";
  const snippet = `<script src="${origin}/widget.js" data-api-key="${draft.api_key}" data-type="chat" data-position="bottom-right" data-allow-toggle="true" async></script>`;
  return <div className="space-y-5 p-4 sm:p-6"><form className="space-y-5" aria-label={tr(`แก้ไข ${row.name}`, `Edit ${row.name}`)} onSubmit={async e => {
    e.preventDefault(); setError(""); setSaving(true);
    try { await saveChannelDraft(row, draft, renewal); onSaved(); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : tr("บันทึกไม่สำเร็จ ลองอีกครั้ง", "Could not save. Try again.")); }
    finally { setSaving(false); }
  }}>
    <div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold">{tr("แก้ไขการตั้งค่า", "Edit settings")}</h2><p className="mt-1 text-sm text-fg-2">{row.team_name} · {row.name}</p></div><Button type="button" variant="ghost" size="icon" onClick={close} disabled={saving} title={tr("ปิดการแก้ไข", "Close editor")} aria-label={tr("ปิดการแก้ไข", "Close editor")}><X /></Button></div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
      <label className="text-sm font-medium">{tr("ชื่อช่องทาง", "Channel name")}<input ref={nameField} required maxLength={255} value={draft.name} onChange={e => patch({ name: e.target.value })} className={control} /></label>
      <label className="flex items-center gap-3 self-end rounded-lg border border-hairline px-3 py-2.5 text-sm"><input type="checkbox" checked={draft.is_active} onChange={e => patch({ is_active: e.target.checked })} className="size-4 accent-brand" />{tr("เปิดใช้งานช่องทาง", "Enable channel")}</label>
      {row.kind === "web" && <><label className="text-sm font-medium">{tr("โดเมนที่อนุญาต", "Allowed domains")}<textarea rows={2} value={draft.allowed_domains} onChange={e => patch({ allowed_domains: e.target.value })} className={control} /><span className="mt-1 block text-xs text-fg-2">{tr("คั่นด้วยจุลภาค · เว้นว่างเพื่ออนุญาตทุกโดเมน", "Comma separated · empty allows all domains")}</span></label><div className="space-y-3"><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={draft.voice_response_enabled} onChange={e => patch({ voice_response_enabled: e.target.checked })} className="size-4 accent-brand" />{tr("ตอบกลับด้วยเสียง", "Voice replies")}</label><p className="text-xs text-fg-2">{tr("หมดอายุ", "Expires")}: {draft.expires_at ? channelDate(draft.expires_at, locale) : tr("ไม่กำหนด", "Never")}</p><label className="block text-sm font-medium">{tr("ต่ออายุถึง", "Renew until")}<input type="datetime-local" value={renewal} onChange={e => setRenewal(e.target.value)} className={control} /></label></div></>}
    </fieldset>
    {row.kind === "messaging" && <details className="border-t border-hairline pt-4" open={row.status === "incomplete"}><summary className="cursor-pointer py-1 text-sm font-medium focus-visible:outline-brand">{tr("การเชื่อมต่อและ Webhook", "Connection and webhook")}</summary><fieldset disabled={saving} className="mt-4 grid gap-4 sm:grid-cols-2">{fields[row.channel_type].map(([key, label, secret]) => <label key={key} className="text-sm font-medium">{label}<input type={secret ? "password" : "text"} autoComplete="off" value={draft.config[key] || ""} onChange={e => patch({ config: { ...draft.config, [key]: e.target.value } })} className={control} /></label>)}</fieldset><label className="mt-4 block text-sm font-medium">Webhook URL<input readOnly value={draft.config.webhook_url?.startsWith("/") ? `${origin}${draft.config.webhook_url}` : draft.config.webhook_url || ""} className={`${control} text-fg-2`} /></label></details>}
    {row.kind === "web" && <><details className="border-t border-hairline pt-4"><summary className="cursor-pointer py-1 text-sm font-medium">{tr("ลิงก์แชตและโค้ดติดตั้ง", "Chat link and installation")}</summary><div className="mt-4 space-y-4">{chatLink && <label className="block text-sm font-medium">{tr("ลิงก์แชต", "Chat link")}<input readOnly value={chatLink} className={control} /></label>}<label className="block text-sm font-medium">{tr("โค้ดติดตั้งบนเว็บไซต์", "Website embed code")}<textarea readOnly rows={4} value={snippet} className={`${control} font-mono break-all`} /></label><Button type="button" variant="outline" onClick={() => void copy(snippet)}><Copy />{tr("คัดลอกโค้ด", "Copy code")}</Button><p role="status" className="text-xs text-fg-2">{copyNotice}</p></div></details></>}
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4"><span className="flex items-center gap-1.5 text-xs text-fg-2" role="status">{dirty ? tr("มีการเปลี่ยนแปลงที่ยังไม่บันทึก", "Unsaved changes") : <><Check size={14} />{tr("ค่าที่บันทึกไว้", "Saved settings")}</>}</span><div className="flex gap-2"><Button type="button" variant="outline" onClick={close} disabled={saving}>{tr("ยกเลิก", "Cancel")}</Button><Button type="submit" disabled={saving || !dirty || !draft.name.trim()}><Save />{saving ? tr("กำลังบันทึก…", "Saving…") : tr("บันทึก", "Save changes")}</Button></div></div>
  </form>{row.kind === "web" && <details className="border-t border-hairline pt-4" onToggle={e => setThemeOpen(e.currentTarget.open)}><summary className="cursor-pointer py-1 text-sm font-medium">{tr("สี โลโก้ และข้อความต้อนรับ", "Colour, logo and greeting")}</summary>{themeOpen && <div className="mt-4"><WidgetThemeEditor token={localStorage.getItem("adminToken") || ""} keyId={row.id} /></div>}</details>}</div>;
}
