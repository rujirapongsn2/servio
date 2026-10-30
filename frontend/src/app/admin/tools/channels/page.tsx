"use client";

import styles from "./page.module.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { CircleAlert, ExternalLink, Globe2, KeyRound, MessageCircle, Pencil, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/Button";
import ChannelOverviewEditor from "@/components/ChannelOverviewEditor";
import { useAdminLocale } from "@/lib/admin-locale";
import { useTeam } from "@/lib/team-context";
import { workflowRequest } from "@/lib/team-workflow";
import { channelDate, channelIdentity, parseChannelOverview, type OverviewChannel } from "@/lib/channels-overview";

type Inventory = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; rows: OverviewChannel[] };
const control = "h-10 w-full rounded-lg border border-control bg-surface px-3 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";
const grid = "grid grid-cols-[minmax(0,1fr)_auto] gap-3 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,.8fr)_auto] md:items-center md:gap-5";
export default function ChannelsPage() {
  const { locale } = useAdminLocale();
  const { teams: accessibleTeams } = useTeam();
  const tr = (th: string, en: string) => locale === "th" ? th : en;
  const [inventory, setInventory] = useState<Inventory>({ kind: "loading" });
  const [query, setQuery] = useState("");
  const [team, setTeam] = useState("all");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [editing, setEditing] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const editButton = useRef<HTMLButtonElement | null>(null);
  const mounted = useRef(true);
  const load = useCallback(async (signal?: AbortSignal) => {
    setInventory({ kind: "loading" });
    try {
      const rows = parseChannelOverview(await workflowRequest("/channel-overview", { signal }));
      if (!signal?.aborted && mounted.current) setInventory({ kind: "ready", rows });
    } catch (e: unknown) {
      if (!signal?.aborted && mounted.current) setInventory({ kind: "error", message: e instanceof Error ? e.message : "Could not load channels" });
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    const selected = new URLSearchParams(window.location.search).get("team_agent_id");
    if (selected && /^\d+$/.test(selected)) setTeam(selected);
    const controller = new AbortController();
    void load(controller.signal);
    return () => { mounted.current = false; controller.abort(); };
  }, [load]);
  const rows = inventory.kind === "ready" ? inventory.rows : [];
  const teams = useMemo(() => Array.from(new Map([...accessibleTeams.map(team => [String(team.id), team.name] satisfies [string, string]), ...rows.map(row => [String(row.team_id), row.team_name] satisfies [string, string])]).entries()), [accessibleTeams, rows]);
  const visible = rows.filter(row => (team === "all" || String(row.team_id) === team)
    && (type === "all" || row.channel_type === type) && (status === "all" || row.status === status)
    && [row.name, row.team_name, row.channel_type, row.kind === "messaging" ? row.identifier : row.allowed_domains.join(" ")]
      .join(" ").toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const statuses = {
    active: tr("เปิดใช้งาน", "Enabled"), paused: tr("ปิดใช้งาน", "Disabled"),
    incomplete: tr("ตั้งค่าไม่ครบ", "Incomplete"), expired: tr("หมดอายุ", "Expired"),
  };
  const channelName = (row: OverviewChannel) => row.channel_type === "web_widget" ? "Web Chat" : row.channel_type === "line" ? "LINE" : row.channel_type === "facebook" ? "Facebook" : "API";
  const close = () => { setEditing(null); editButton.current?.focus(); };
  return <div className="mx-auto max-w-7xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold tracking-tight">{tr("ช่องทางสนทนา", "Conversation channels")}</h1><p className="mt-2 text-sm text-fg-2">{tr("สรุปและแก้ไขการตั้งค่าช่องทางของทุกทีม", "Review and edit channel settings across teams")}</p></div><Button asChild variant="outline" className="h-10"><Link href="/admin/teams">{tr("จัดการทีมและเพิ่มช่องทาง", "Manage teams and add channels")}<ExternalLink /></Link></Button></header>
    {notice && <p role="status" className="text-sm text-success">{notice}</p>}
    <section aria-label={tr("รายการช่องทาง", "Channel inventory")} className="overflow-hidden rounded-xl border border-hairline bg-surface">
      <fieldset disabled={editing !== null} className="grid grid-cols-2 gap-3 border-b border-hairline p-4 lg:grid-cols-[minmax(0,2fr)_1fr_1fr_1fr] disabled:opacity-60">
        <label className="text-xs font-medium text-fg-2">{tr("ค้นหาช่องทาง", "Search channels")}<span className="relative mt-1.5 block"><Search aria-hidden="true" size={16} className="absolute left-3 top-3 text-icon" /><input type="search" value={query} onChange={e => setQuery(e.target.value)} className={`${control} pl-9`} /></span></label>
        <label className="text-xs font-medium text-fg-2">{tr("ทีม", "Team")}<select value={team} onChange={e => setTeam(e.target.value)} className={`${control} mt-1.5`}><option value="all">{tr("ทุกทีม", "All teams")}</option>{teams.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
        <label className="text-xs font-medium text-fg-2">{tr("ประเภทช่องทาง", "Channel type")}<select value={type} onChange={e => setType(e.target.value)} className={`${control} mt-1.5`}><option value="all">{tr("ทุกประเภท", "All types")}</option><option value="web_widget">Web Chat</option><option value="line">LINE</option><option value="facebook">Facebook</option><option value="api">API</option></select></label>
        <label className="text-xs font-medium text-fg-2">{tr("สถานะ", "Status")}<select value={status} onChange={e => setStatus(e.target.value)} className={`${control} mt-1.5`}><option value="all">{tr("ทุกสถานะ", "All statuses")}</option>{Object.entries(statuses).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      </fieldset>
      <div className="flex items-center justify-between gap-3 border-b border-hairline px-4 py-3"><p role="status" className="text-sm text-fg-2">{inventory.kind === "ready" ? tr(`${visible.length} จาก ${rows.length} ช่องทาง`, `${visible.length} of ${rows.length} channels`) : inventory.kind === "error" ? tr("โหลดข้อมูลไม่สำเร็จ", "Channels unavailable") : tr("กำลังโหลดข้อมูลช่องทาง", "Loading channels")}</p><Button variant="ghost" size="icon" onClick={() => void load()} disabled={inventory.kind === "loading" || editing !== null} aria-label={tr("โหลดช่องทางใหม่", "Refresh channels")} title={tr("โหลดช่องทางใหม่", "Refresh channels")}><RefreshCw className={inventory.kind === "loading" ? "animate-spin motion-reduce:animate-none" : ""} /></Button></div>
      {inventory.kind === "loading" ? <div role="status" className="space-y-4 p-5">{[0, 1, 2].map(i => <div key={i} className="h-16 animate-pulse rounded-lg bg-app motion-reduce:animate-none" />)}<span className="sr-only">{tr("กำลังโหลด…", "Loading…")}</span></div>
        : inventory.kind === "error" ? <div className="space-y-3 p-8"><p role="alert" className="flex items-center gap-2 text-sm text-danger"><CircleAlert size={18} />{tr("โหลดช่องทางไม่สำเร็จ", "Could not load channels")}</p><p className="text-sm text-fg-2">{inventory.message}</p><Button variant="outline" onClick={() => void load()}>{tr("ลองอีกครั้ง", "Retry")}</Button></div>
        : visible.length === 0 ? <div className="space-y-3 px-5 py-12 text-center"><SlidersHorizontal className="mx-auto text-icon" size={28} /><h2 className="font-semibold">{rows.length ? tr("ไม่พบช่องทางตามตัวกรอง", "No matching channels") : tr("ยังไม่มีช่องทางที่ตั้งค่าไว้", "No configured channels")}</h2>{rows.length ? <Button variant="outline" onClick={() => { setTeam("all"); setType("all"); setStatus("all"); setQuery(""); }}>{tr("ล้างตัวกรอง", "Clear filters")}</Button> : <Link href="/admin/teams" className="text-sm text-brand underline underline-offset-4">{tr("เพิ่มช่องทางในทีมผู้ช่วย AI", "Add a channel in Team Agents")}</Link>}</div>
        : <><div aria-hidden="true" className={`${grid} hidden border-b border-hairline bg-app px-5 py-3 text-xs font-medium text-fg-2 md:grid`}><span>{tr("ช่องทาง", "Channel")}</span><span>{tr("ทีม", "Team")}</span><span>{tr("การตั้งค่า", "Settings")}</span><span>{tr("สถานะ / อัปเดตล่าสุด", "Status / last updated")}</span><span className="w-28">{tr("การจัดการ", "Actions")}</span></div><ul className={`${styles.inventory} divide-y divide-hairline`}>{visible.map(row => {
          const id = channelIdentity(row); const opened = editing === id;
          const Icon = row.channel_type === "web_widget" ? Globe2 : row.channel_type === "api" ? KeyRound : MessageCircle;
          return <li key={id} className={opened ? "bg-selected" : ""}><div className={`${grid} px-4 py-4 sm:px-5`}>
            <div className="flex min-w-0 items-start gap-3"><div className="mt-0.5 rounded-lg bg-app p-2 text-icon"><Icon aria-hidden="true" size={18} /></div><div className="min-w-0"><h2 className="break-words text-sm font-semibold">{row.name}</h2><p className="mt-1 text-xs text-fg-2">{channelName(row)}<span className="md:hidden"> · {row.team_name}</span></p></div></div>
            <div className="hidden min-w-0 text-sm md:block"><span className="mr-2 text-xs text-fg-2 md:hidden">{tr("ทีม", "Team")}</span>{row.team_id === null ? row.team_name : <Link href={`/admin/teams/${row.team_id}/workflow`} className="break-words hover:text-brand hover:underline">{row.team_name}</Link>}{!row.team_active && <p className="mt-1 text-xs text-fg-2">{tr("ทีมปิดใช้งาน", "Team disabled")}</p>}</div>
            <div className="col-span-2 row-start-2 min-w-0 space-y-1 text-xs text-fg-2 md:col-span-1 md:row-auto">{row.kind === "web" ? <><p className="break-words">{row.allowed_domains.length ? row.allowed_domains.join(", ") : tr("ทุกโดเมน", "All domains")}</p><p>{row.voice_response_enabled ? tr("ข้อความและเสียง", "Text and voice") : tr("ข้อความ", "Text only")}{row.expires_at && <> · {tr("หมดอายุ", "Expires")} {channelDate(row.expires_at, locale)}</>}</p></> : <><p>{row.identifier ? `${row.channel_type === "line" ? "Channel" : "Page"} ID: ${row.identifier}` : tr("ยังไม่ระบุบัญชี", "No account ID")}</p><p>{tr(`ตั้งค่าแล้ว ${row.configured_fields.length}/${row.required_fields.length} รายการ`, `${row.configured_fields.length}/${row.required_fields.length} fields configured`)}</p></>}</div>
            <div className="col-start-2 row-start-1 justify-self-end md:col-auto md:row-auto md:justify-self-start"><span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ${row.status === "active" ? "bg-success/10 text-success" : row.status === "paused" ? "bg-app text-fg-2" : "bg-danger/10 text-danger"}`}><span className="size-1.5 rounded-full bg-current" aria-hidden="true" />{statuses[row.status]}</span><p className="mt-1.5 text-xs text-fg-2">{channelDate(row.updated_at, locale)}</p></div>
            <div className="col-span-2 row-start-3 flex w-auto items-center justify-end gap-1 md:col-span-1 md:row-auto md:w-28 md:justify-start"><Button variant="outline" className="h-9" disabled={!row.can_edit || editing !== null} aria-expanded={opened} aria-controls={`editor-${id}`} title={!row.can_edit ? tr("ต้องมีสิทธิ์ผู้ดูแลทีม", "Team admin permission required") : undefined} onClick={e => { editButton.current = e.currentTarget; setNotice(""); setEditing(id); }}><Pencil />{tr("แก้ไข", "Edit")}</Button>{row.kind === "web" && row.slug && row.status === "active" && <Button asChild variant="ghost" size="icon"><a href={`/c/${row.slug}?type=chat`} target="_blank" rel="noopener noreferrer" title={tr("เปิดแชต", "Open chat")} aria-label={tr(`เปิดแชต ${row.name}`, `Open ${row.name} chat`)}><ExternalLink /></a></Button>}</div>
          </div>{opened && <div id={`editor-${id}`} className="border-t border-hairline"><ChannelOverviewEditor row={row} onClose={close} onSaved={() => { close(); setNotice(tr("บันทึกการตั้งค่าแล้ว", "Settings saved")); void load(); }} /></div>}</li>;
        })}</ul></>}
    </section>
  </div>;
}
