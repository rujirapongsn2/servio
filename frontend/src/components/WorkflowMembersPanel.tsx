"use client";
import { useAdminLocale } from "@/lib/admin-locale";

import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, X } from "lucide-react";
import { workflowRequest, type TeamWorkflow } from "@/lib/team-workflow";

type MemberOption = { id: number; name: string; model: string; shared: boolean; membership_count: number };
export default function WorkflowMembersPanel({ workflow, busy, onClose, onSave }: {
  workflow: TeamWorkflow; busy: boolean; onClose: () => void;
  onSave: (memberIds: number[], fallbackId: number | null, expectedIds: number[], expectedFallback: number | null) => Promise<void>;
}) {
  const { copy } = useAdminLocale();
  const [initial] = useState(() => ({ ids: workflow.agents.map((agent) => agent.id), fallback: workflow.fallback_agent_id }));
  const [options, setOptions] = useState<MemberOption[]>([]);
  const [ids, setIds] = useState(workflow.agents.map((agent) => agent.id));
  const [fallback, setFallback] = useState(workflow.fallback_agent_id);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    void workflowRequest(`/team-agents/${workflow.team_id}/workflow/member-options`, { signal: controller.signal }).then((data) => {
      if (controller.signal.aborted) return;
      if (!data || typeof data !== "object" || !("agents" in data) || !Array.isArray(data.agents) || !data.agents.every((item: unknown) => item && typeof item === "object" && "id" in item && typeof item.id === "number" && Number.isSafeInteger(item.id) && item.id > 0 && "name" in item && typeof item.name === "string" && "model" in item && typeof item.model === "string" && "shared" in item && typeof item.shared === "boolean" && "membership_count" in item && typeof item.membership_count === "number" && Number.isSafeInteger(item.membership_count) && item.membership_count >= 0)) throw Error("Invalid member options.");
      setOptions(data.agents); setLoading(false);
    }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : "Unable to load agents."); setLoading(false); } });
    return () => controller.abort();
  }, [workflow.team_id]);
  const toggle = (id: number, checked: boolean) => {
    const next = checked ? [...ids, id] : ids.filter((current) => current !== id);
    setIds(next); if (!next.includes(fallback ?? -1)) setFallback(next[0] ?? null);
  };
  const move = (id: number, direction: number) => {
    const index = ids.indexOf(id); const next = [...ids];
    [next[index], next[index + direction]] = [next[index + direction], next[index]]; setIds(next);
  };
  const save = async () => {
    const removed = workflow.agents.filter((agent) => !ids.includes(agent.id));
    if (removed.length && !window.confirm(copy.confirmRemoveMembers(removed.map((agent) => agent.name).join(", ")))) return;
    setError(""); try { await onSave(ids, fallback, initial.ids, initial.fallback); } catch (failure: unknown) { setError(failure instanceof Error ? failure.message : "Unable to save members."); }
  };
  const ordered = [...ids.map((id) => options.find((option) => option.id === id)).filter((item): item is MemberOption => Boolean(item)), ...options.filter((item) => !ids.includes(item.id))];
  return <section aria-label={copy.teamMembers} className="rounded-xl border border-slate-200 bg-white p-4">
    <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">{copy.teamMembers}</h2><button type="button" aria-label={copy.closeMembers} disabled={busy} onClick={onClose} className="rounded p-2"><X className="h-4 w-4" /></button></div>
    {error && <div role="alert" className="mb-3 text-sm text-red-700">{copy.membersFailed}<details><summary>{copy.errorDetails}</summary>{error}</details></div>}
    {loading && <p role="status" className="text-sm text-slate-500">{copy.loadingAgents}</p>}
    <fieldset disabled={busy || loading} className="space-y-2">{ordered.map((agent) => <div key={agent.id} className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
      <label className="flex min-w-0 flex-1 items-center gap-2"><input type="checkbox" checked={ids.includes(agent.id)} data-admin-write="true" onChange={(event) => toggle(agent.id, event.target.checked)} /><span className="break-words">{agent.name}</span>{agent.membership_count > 1 && <span className="text-xs text-amber-700">{copy.shared}</span>}</label>
      {ids.includes(agent.id) && <><label className="flex items-center gap-1 text-xs"><input type="radio" aria-label={copy.useNamedFallback(agent.name)} name="workflow-member-fallback" checked={fallback === agent.id} data-admin-write="true" onChange={() => setFallback(agent.id)} />{copy.fallback}</label>
        <button type="button" aria-label={copy.moveNamedUp(agent.name)} title={copy.moveNamedUp(agent.name)} disabled={ids.indexOf(agent.id) === 0} data-admin-write="true" onClick={() => move(agent.id, -1)} className="p-1 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
        <button type="button" aria-label={copy.moveNamedDown(agent.name)} title={copy.moveNamedDown(agent.name)} disabled={ids.indexOf(agent.id) === ids.length - 1} data-admin-write="true" onClick={() => move(agent.id, 1)} className="p-1 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button></>}
    </div>)}</fieldset>
    <div className="mt-3 flex justify-end"><button type="button" disabled={busy || loading || Boolean(error && options.length === 0)} data-admin-write="true" onClick={() => void save()} className="rounded-lg bg-sky-600 px-4 py-2 text-sm text-white disabled:opacity-40">{busy ? copy.saving : copy.saveMembers}</button></div>
  </section>;
}
