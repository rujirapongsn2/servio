"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Code, Copy, ExternalLink, MessageSquare, Plus, RefreshCw } from "lucide-react";
import { workflowRequest } from "@/lib/team-workflow";
import { parseWorkflowWebChats, workflowChatEmbed, workflowChatUrl, type WorkflowWebChat } from "@/lib/workflow-channels";
import WorkflowPanelDialog from "@/components/WorkflowPanelDialog";

type ChannelDialog = { kind: "closed" } | { kind: "create"; phase: "confirm" | "sending" | "refresh"; message: string } | { kind: "embed"; channel: WorkflowWebChat };
const button = "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:opacity-40";

export default function WorkflowChannels({ teamId, teamName, canEdit, hasDrafts }: {
  teamId: number; teamName: string; canEdit: boolean; hasDrafts: boolean;
}) {
  const [channels, setChannels] = useState<WorkflowWebChat[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<ChannelDialog>({ kind: "closed" });
  const [name, setName] = useState(`${teamName} Web Chat`);
  const active = useRef(false);
  const mounted = useRef(true);
  const load = useCallback(async (signal?: AbortSignal) => {
    const data = parseWorkflowWebChats(await workflowRequest(`/api-keys?team_agent_id=${teamId}`, { signal }), teamId);
    if (signal?.aborted || !mounted.current) return [];
    setChannels(data);
    setSelected(previous => data.some(item => item.id === previous) ? previous : data[0]?.id ?? null);
    return data;
  }, [teamId]);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    setLoading(true); setError("");
    void load(controller.signal).catch(() => { if (!controller.signal.aborted) setError("Unable to load channels. Try again."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { mounted.current = false; controller.abort(); };
  }, [load]);
  const refresh = async () => {
    setLoading(true); setError("");
    try { await load(); } catch { if (mounted.current) setError("Unable to load channels. Try again."); }
    finally { if (mounted.current) setLoading(false); }
  };
  const create = async () => {
    if (active.current || !name.trim() || !canEdit) return;
    active.current = true;
    setDialog({ kind: "create", phase: "sending", message: "" });
    try {
      await workflowRequest("/api-keys", { method: "POST", body: JSON.stringify({ name: name.trim(), team_agent_id: teamId, channel_type: "web_widget", voice_response_enabled: false }) });
      if (!mounted.current) return;
      const previousIds = new Set(channels.map(item => item.id));
      const updated = await load();
      if (!mounted.current) return;
      const created = updated.find(item => !previousIds.has(item.id) && item.name === name.trim());
      if (created) setSelected(created.id);
      setDialog({ kind: "closed" }); setNotice("Web Chat created. Uses saved team settings.");
    } catch {
      if (mounted.current) setDialog({ kind: "create", phase: "refresh", message: "Creation could not be confirmed. Refresh channels before creating another." });
    } finally { active.current = false; }
  };
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setNotice("Copied"); }
    catch { setNotice("Copy unavailable. Select and copy the text below."); }
  };
  const chosen = channels.find(item => item.id === selected);
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const url = chosen ? workflowChatUrl(origin, chosen) : "";
  return <section aria-label="Team channels" className="mx-auto w-full max-w-4xl space-y-4 py-4 sm:py-8">
    <div><h2 className="text-xl font-semibold text-slate-900">Channels for {teamName}</h2><p className="mt-1 text-sm text-slate-500">Private preview does not need a channel.</p></div>
    {hasDrafts && <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Unsaved Agent changes are only used in preview. Channels use saved settings.</p>}
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3"><MessageSquare className="h-6 w-6 text-sky-600" /><h3 className="flex-1 font-semibold">Web Chat</h3>
        <button type="button" disabled={loading} className={button} onClick={() => void refresh()} aria-label="Refresh channels" title="Refresh channels"><RefreshCw size={16} /></button>
        {canEdit && <button type="button" className={button} onClick={() => { setName(`${teamName} Web Chat`); setDialog({ kind: "create", phase: "confirm", message: "" }); }}><Plus size={16} />New Web Chat</button>}</div>
      {loading ? <p role="status" className="text-sm text-slate-500">Loading channels…</p> : chosen ? <>
        <label className="block text-sm font-medium">Use existing Web Chat<select className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2" value={selected ?? ""} onChange={event => { setSelected(Number(event.target.value)); setNotice(""); }}>{channels.map(channel => <option key={channel.id} value={channel.id}>{channel.name}</option>)}</select></label>
        <label className="block text-sm font-medium">Chat link<input readOnly value={url} className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm" onFocus={event => event.currentTarget.select()} /></label>
        <div className="flex flex-wrap gap-2"><a href={url} target="_blank" rel="noopener noreferrer" className={`${button} border-sky-600 bg-sky-600 text-white`}><ExternalLink size={16} />Open Web Chat</a><button className={button} type="button" onClick={() => void copy(url)}><Copy size={16} />Copy link</button>{canEdit && <button type="button" className={button} onClick={() => setDialog({ kind: "embed", channel: chosen })}><Code size={16} />Embed</button>}</div>
      </> : <div className="py-5 text-center text-sm text-slate-500">No active Web Chat. {canEdit ? "Create one when ready to share your team." : "Ask a team admin to create one."}</div>}
    </div>
    <p role="status" className="min-h-5 text-sm text-slate-600">{notice}</p>
    <a href={`/admin/tools/channels?team_agent_id=${teamId}`} className="inline-flex items-center gap-2 text-sm text-sky-700 underline">Other channels and advanced settings<ExternalLink size={14} /></a>
    {dialog.kind === "create" && <WorkflowPanelDialog title="Create Web Chat" onClose={() => setDialog({ kind: "closed" })} busy={dialog.phase === "sending"}>
      <form className="mx-auto max-w-xl space-y-4" onSubmit={event => { event.preventDefault(); if (dialog.phase === "confirm") void create(); }}>
        <label className="block text-sm font-medium">Channel name<input required maxLength={100} disabled={dialog.phase !== "confirm"} value={name} onChange={event => setName(event.target.value)} className="mt-2 w-full rounded-lg border px-3 py-2" /></label>
        <p className="text-sm text-slate-600">Creates a customer chat link for {teamName} using saved settings. Anyone with the link can start a chat.</p>
        {dialog.message && <p role="alert" className="text-sm text-amber-800">{dialog.message}</p>}
        <div className="flex flex-wrap justify-end gap-2"><button type="button" className={button} disabled={dialog.phase === "sending"} onClick={() => setDialog({ kind: "closed" })}>Cancel</button>{dialog.phase === "refresh" ? <button type="button" className={button} disabled={loading} onClick={async () => { await refresh(); if (mounted.current) setDialog({ kind: "closed" }); }}>Refresh channels</button> : <button type="submit" disabled={dialog.phase === "sending" || !name.trim()} className={`${button} bg-sky-600 text-white`}>{dialog.phase === "sending" ? "Creating…" : "Create Web Chat"}</button>}</div>
      </form>
    </WorkflowPanelDialog>}
    {dialog.kind === "embed" && <WorkflowPanelDialog title={`Embed ${dialog.channel.name}`} onClose={() => setDialog({ kind: "closed" })}><label className="block text-sm font-medium">Website embed code<textarea readOnly rows={5} value={workflowChatEmbed(origin, dialog.channel)} onFocus={event => event.currentTarget.select()} className="mt-2 w-full rounded-lg border p-3 font-mono text-xs" /></label><button type="button" className={`${button} mt-3`} onClick={() => void copy(workflowChatEmbed(origin, dialog.channel))}><Copy size={16} />Copy code</button></WorkflowPanelDialog>}
  </section>;
}
