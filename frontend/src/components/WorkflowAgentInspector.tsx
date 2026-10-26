"use client";
import { useAdminLocale } from "@/lib/admin-locale";

import { useEffect, useState } from "react";
import { BookOpen, Bot, Expand, GitBranch, LockKeyhole, Plus, Save, Star, Wrench, X, Play, Sparkles, Trash2 } from "lucide-react";
import { parseDefaultChatModels, parseModelIds } from "@/lib/provider-models";
import { isKnowledgeTool, workflowRequest, type TeamWorkflow, type WorkflowAgentDraft } from "@/lib/team-workflow";
import type { WorkflowEditor } from "@/lib/workflow-authoring";

type Section = "agent" | "tools" | "knowledge" | "handoffs";
const sections = [
  { id: "agent", icon: Bot },
  { id: "tools", icon: Wrench },
  { id: "knowledge", icon: BookOpen },
  { id: "handoffs", icon: GitBranch },
] satisfies { id: Section; icon: typeof Bot }[];
const inputClass = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500 disabled:bg-slate-50";

export default function WorkflowAgentInspector({ workflow, editor, dirty, saving, locked = false, onChange, onSave, onDiscard, onCreateTool, onCreateKnowledge, onTest, onDelete, onCreateProvider }: {
  workflow: TeamWorkflow;
  editor: WorkflowEditor;
  dirty: boolean;
  saving: boolean;
  locked?: boolean;
  onChange: (draft: WorkflowAgentDraft) => void;
  onSave: () => void;
  onDiscard: () => void;
  onCreateTool: () => void;
  onCreateKnowledge: () => void;
  onTest?: () => void;
  onDelete?: (replacementFallbackId: number | null) => void;
  onCreateProvider?: () => void;
}) {
  const { copy } = useAdminLocale();
  const agent = editor.kind === "existing" ? editor.agent : null;
  const draft = editor.draft;
  const [section, setSection] = useState<Section>("agent");
  const [expanded, setExpanded] = useState(false);
  const [catalog, setCatalog] = useState<{ providerId: number | null; status: "loading" | "unavailable" | "idle"; models: string[] }>({ providerId: draft.llm_provider_id, status: "loading", models: [] });
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const models = catalog.providerId === draft.llm_provider_id ? catalog.models : [];
  const modelStatus = catalog.providerId === draft.llm_provider_id ? catalog.status : "loading";
  const unchangedModel = agent !== null && agent.model === draft.model.trim() && agent.llm_provider_id === draft.llm_provider_id;
  const validModel = draft.llm_provider_id !== null || unchangedModel || (modelStatus === "idle" && models.includes(draft.model));
  const [optimizing, setOptimizing] = useState(false);
  const [optimization, setOptimization] = useState<{ original: string; result: string } | null>(null);
  const [optimizeError, setOptimizeError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [replacement, setReplacement] = useState<number | null>(workflow.agents.find((item) => item.id !== agent?.id)?.id ?? null);
  const optimize = async () => {
    if (optimizing || !draft.instructions.trim()) return;
    const original = draft.instructions; setOptimizing(true); setOptimizeError("");
    try {
      const data = await workflowRequest(`/agents/optimize-prompt?team_agent_id=${workflow.team_id}`, { method: "POST", body: JSON.stringify({ instructions: original, agent_name: draft.name, model: draft.model.trim(), llm_provider_id: draft.llm_provider_id }) });
      if (!data || typeof data !== "object" || !("optimized_instructions" in data) || typeof data.optimized_instructions !== "string" || !data.optimized_instructions.trim()) throw Error("Invalid optimization response.");
      setOptimization({ original, result: data.optimized_instructions });
    } catch (failure: unknown) { setOptimizeError(failure instanceof Error ? failure.message : "Unable to optimize instructions."); }
    finally { setOptimizing(false); }
  };
  const readOnly = !workflow.can_edit || agent?.shared === true || locked;
  const stale = agent !== null && draft.expected_updated_at !== agent.updated_at;

  useEffect(() => {
    const controller = new AbortController();
    const providerId = draft.llm_provider_id;
    setCatalog({ providerId, status: "loading", models: [] });
    const load = async (endpoint: string, registered: boolean) => {
      const data = await workflowRequest(`/llm-providers/${draft.llm_provider_id}/${endpoint}`, { signal: controller.signal });
      const ids = parseModelIds(data, registered);
      if (!controller.signal.aborted) setCatalog((previous) => ({ ...previous, models: Array.from(new Set([...previous.models, ...ids])) }));
      return ids;
    };
    const requests = draft.llm_provider_id === null ? [
      workflowRequest("/default-chat-models", { signal: controller.signal }).then((data) => {
        const result = parseDefaultChatModels(data);
        if (!controller.signal.aborted) setCatalog({ providerId, status: "loading", models: result.models });
      }),
    ] : [load("models", false), load("registered-models", true)];
    void Promise.allSettled(requests).then((results) => {
      if (controller.signal.aborted) return;
      setCatalog((previous) => ({ ...previous, status: results.some((result) => result.status === "rejected") ? "unavailable" : "idle" }));
    });
    return () => controller.abort();
  }, [draft.llm_provider_id, catalogAttempt]);

  useEffect(() => {
    if (!expanded) return;
    const previous = document.activeElement;
    const editor = document.getElementById("workflow-instructions-expanded");
    editor?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
      if (event.key === "Tab") {
        const close = document.getElementById("workflow-instructions-close");
        event.preventDefault();
        if (document.activeElement === editor) close?.focus(); else editor?.focus();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, [expanded]);

  const instructionsEditor = (full: boolean) => (
    <textarea id={full ? "workflow-instructions-expanded" : "workflow-instructions"} aria-label={copy.instructions} required
      readOnly={readOnly} disabled={saving} value={draft.instructions} rows={full ? 24 : 12}
      data-admin-write="true" onChange={(event) => onChange({ ...draft, instructions: event.target.value })}
      className={`${inputClass} resize-y leading-relaxed ${full ? "min-h-0 flex-1 resize-none" : "min-h-56"}`} />
  );

  return (
    <form aria-label={copy.agentSettings} onSubmit={(event) => { event.preventDefault(); if (validModel) onSave(); }} className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white lg:h-full lg:max-h-full lg:min-h-0">
      <div className="border-b border-slate-200 p-4">
        <div className="flex items-center justify-between gap-2"><h2 className="break-words text-lg font-semibold text-slate-900">{agent?.name || copy.newAgent}</h2>
        <div className="flex shrink-0 gap-1">{agent && onTest && <button type="button" disabled={saving || locked || !validModel} onClick={onTest} aria-label={copy.chatWithNamedAgent(agent.name)} title={copy.chatWithNamedAgent(agent.name)} className="inline-flex items-center gap-1.5 rounded-lg border border-sky-200 px-2 py-1.5 text-sm text-sky-700"><Play className="h-4 w-4" />{copy.chat}</button>}
        {agent && !readOnly && onDelete && <button type="button" disabled={saving} onClick={() => setDeleting(!deleting)} data-admin-write="true" aria-label={copy.deleteAgent} title={copy.deleteAgent} className="rounded p-2 text-red-600"><Trash2 className="h-4 w-4" /></button>}</div></div>
        {deleting && agent && <div className="mt-3 space-y-2 rounded-lg border border-red-200 p-3 text-sm"><p>{copy.deleteNamedAgentPermanently(agent.name)}</p>
          {agent.id === workflow.fallback_agent_id && workflow.agents.length > 1 && <label className="block">{copy.replacementFallback}<select aria-label={copy.replacementFallback} className={inputClass} value={replacement ?? ""} onChange={(event) => setReplacement(Number(event.target.value))}>{workflow.agents.filter((item) => item.id !== agent.id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
          <button type="button" disabled={saving} data-admin-write="true" onClick={() => onDelete?.(agent.id === workflow.fallback_agent_id ? replacement : workflow.fallback_agent_id)} className="text-red-700 underline">{copy.confirmPermanentDelete}</button>
        </div>}
        {agent?.shared && <p role="status" className="mt-2 flex items-start gap-2 text-xs text-amber-800"><LockKeyhole className="h-4 w-4 shrink-0" />{copy.sharedAgentReadOnly}</p>}
        {!workflow.can_edit && <p className="mt-1 text-xs text-slate-500">{copy.readOnly}</p>}
      </div>
      <div role="tablist" aria-label={copy.settingsSections} className="grid grid-cols-4 gap-1 border-b border-slate-200 p-2">
        {sections.map(({ id, icon: Icon }) => <button key={id} id={`workflow-tab-${id}`} type="button" role="tab" aria-selected={section === id}
          aria-controls="workflow-inspector-panel" tabIndex={section === id ? 0 : -1} onClick={() => setSection(id)}
          onKeyDown={(event) => {
            const index = sections.findIndex((item) => item.id === id);
            const target = event.key === "ArrowRight" ? sections[(index + 1) % sections.length]
              : event.key === "ArrowLeft" ? sections[(index + sections.length - 1) % sections.length]
              : event.key === "Home" ? sections[0] : event.key === "End" ? sections[sections.length - 1] : null;
            if (target) { event.preventDefault(); setSection(target.id); document.getElementById(`workflow-tab-${target.id}`)?.focus(); }
          }}
          className={`flex min-w-0 flex-col items-center gap-1 rounded-lg px-1 py-2 text-[11px] font-medium focus-visible:outline-sky-500 ${section === id ? "bg-sky-50 text-sky-700" : "text-slate-500 hover:bg-slate-50"}`}>
          <Icon className="h-4 w-4" />{id === "agent" ? copy.agent : id === "tools" ? copy.toolsTab : id === "knowledge" ? copy.knowledge : copy.handoffs}
        </button>)}
      </div>
      <div id="workflow-inspector-panel" role="tabpanel" aria-labelledby={`workflow-tab-${section}`} className="min-h-0 flex-1 overflow-y-auto p-4">
        {stale && <p role="alert" className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{copy.staleDraft}</p>}
        <fieldset disabled={readOnly || saving} className="space-y-4 disabled:opacity-75">
          {section === "agent" && <>
            <div><label htmlFor="workflow-agent-name" className="mb-1 block text-sm font-medium">{copy.name}</label>
              <input id="workflow-agent-name" required maxLength={255} pattern={".*\\S.*"} value={draft.name} data-admin-write="true" onChange={(event) => onChange({ ...draft, name: event.target.value })} className={inputClass} /></div>
            <div><div className="mb-1 flex items-center justify-between"><label htmlFor="workflow-provider" className="block text-sm font-medium">{copy.provider}</label>{onCreateProvider && <button type="button" onClick={onCreateProvider} data-admin-write="true" aria-label={copy.createProvider} title={copy.createProvider} className="rounded p-1 text-sky-700"><Plus className="h-4 w-4" /></button>}</div>
              <select id="workflow-provider" value={draft.llm_provider_id ?? "default"}
                data-admin-write="true" onChange={(event) => onChange({ ...draft, llm_provider_id: event.target.value === "default" ? null : Number(event.target.value), model: "" })} className={inputClass}>
                <option value="default">{copy.defaultProvider}</option>
                {workflow.providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
                {draft.llm_provider_id !== null && !workflow.providers.some((provider) => provider.id === draft.llm_provider_id) && <option value={draft.llm_provider_id}>{copy.currentProvider}</option>}
              </select></div>
            <div><label htmlFor="workflow-model" className="mb-1 block text-sm font-medium">{copy.model}</label>
              {draft.llm_provider_id === null ? <>
                <select id="workflow-model" required value={unchangedModel || models.includes(draft.model) ? draft.model : ""} disabled={modelStatus !== "idle"} data-admin-write="true"
                  onChange={(event) => onChange({ ...draft, model: event.target.value })} className={inputClass}>
                  <option value="">{copy.chooseChatModel}</option>
                  {unchangedModel && draft.model && !models.includes(draft.model) && <option value={draft.model} disabled>{draft.model} ({copy.previousModel})</option>}
                  {models.map((model) => <option key={model} value={model}>{model}</option>)}
                </select>
                {modelStatus === "idle" && models.length === 0 && <p role="status" className="mt-1 text-xs text-slate-500">{copy.noChatModels}</p>}
                {modelStatus === "unavailable" && <div role="status" className="mt-1 flex items-center gap-2 text-xs text-slate-500">{copy.chatModelsUnavailable}<button type="button" onClick={() => setCatalogAttempt((attempt) => attempt + 1)} className="text-sky-700 underline">{copy.retryChatModels}</button></div>}
                {modelStatus === "loading" && <p role="status" className="mt-1 text-xs text-slate-500">{copy.modelLoading}</p>}
              </> : <>
                <input id="workflow-model" list="workflow-models" required maxLength={100} pattern={".*\\S.*"} value={draft.model} data-admin-write="true" onChange={(event) => onChange({ ...draft, model: event.target.value })} className={inputClass} />
                <datalist id="workflow-models">{models.map((model) => <option key={model} value={model} />)}</datalist>
                {modelStatus !== "idle" && <p role="status" className="mt-1 text-xs text-slate-500">{modelStatus === "loading" ? copy.modelLoading : copy.modelUnavailable}</p>}
              </>}</div>
            <div><div className="mb-1 flex items-center justify-between"><label htmlFor="workflow-instructions" className="text-sm font-medium">{copy.instructions}</label>
              <button type="button" aria-label={copy.expandInstructions} title={copy.expandInstructions} onClick={() => setExpanded(true)} className="rounded p-1 text-slate-500 hover:bg-slate-100"><Expand className="h-4 w-4" /></button></div>
              {instructionsEditor(false)}
              <button type="button" data-admin-write="true" disabled={optimizing || !validModel || !draft.instructions.trim() || !draft.model.trim()} onClick={() => void optimize()} className="mt-2 inline-flex items-center gap-1.5 text-sm text-sky-700 disabled:opacity-40"><Sparkles className="h-4 w-4" />{optimizing ? copy.optimizing : copy.optimize}</button>
              {optimizeError && <div role="alert" className="mt-2 text-sm text-red-700">{copy.optimizeFailed}<details><summary>{copy.errorDetails}</summary>{optimizeError}</details></div>}
              {optimization && <div className="mt-3 space-y-2 rounded-lg border p-3"><label className="block text-sm font-medium">{copy.suggestedInstructions}<textarea aria-label={copy.suggestedInstructions} readOnly value={optimization.result} rows={12} className={inputClass} /></label>
                {draft.instructions !== optimization.original && <p role="status" className="text-xs text-amber-800">{copy.instructionsChanged}</p>}
                <div className="flex gap-3"><button type="button" disabled={draft.instructions !== optimization.original} onClick={() => { onChange({ ...draft, instructions: optimization.result }); setOptimization(null); }} className="text-sm text-sky-700 disabled:opacity-40">{copy.applySuggestion}</button><button type="button" onClick={() => setOptimization(null)} className="text-sm text-slate-600">{copy.dismiss}</button></div></div>}
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.is_fallback} disabled={agent !== null && agent.id === workflow.fallback_agent_id}
              data-admin-write="true" onChange={(event) => onChange({ ...draft, is_fallback: event.target.checked })} /><Star className="h-4 w-4 text-amber-600" />{copy.useFallback}</label>
          </>}
          {(section === "tools" || section === "knowledge") && <>
            <div className="flex justify-end"><button type="button" data-admin-write="true" onClick={section === "knowledge" ? onCreateKnowledge : onCreateTool} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm text-sky-700 hover:bg-sky-50"><Plus className="h-4 w-4" />{section === "knowledge" ? copy.createKnowledge : copy.createTool}</button></div>
            {workflow.tools.filter((tool) => isKnowledgeTool(tool) === (section === "knowledge")).map((tool) => <label key={tool.id} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 text-sm">
              <input className="mt-1" type="checkbox" checked={draft.tool_ids.includes(tool.id)} disabled={tool.name === "DateTimeTool"}
                data-admin-write="true" onChange={(event) => onChange({ ...draft, tool_ids: event.target.checked ? [...draft.tool_ids, tool.id] : draft.tool_ids.filter((id) => id !== tool.id) })} />
              <span className="min-w-0 break-words">{tool.name}</span>
            </label>)}
            {!workflow.tools.some((tool) => isKnowledgeTool(tool) === (section === "knowledge")) && <p className="py-6 text-center text-sm text-slate-500">{section === "knowledge" ? copy.noKnowledge : copy.noTools}</p>}
          </>}
          {section === "handoffs" && <>
            {workflow.agents.filter((target) => target.id !== agent?.id).map((target) => <label key={target.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm">
              <input type="checkbox" checked={draft.handoff_agent_ids.includes(target.id)}
                data-admin-write="true" onChange={(event) => onChange({ ...draft, handoff_agent_ids: event.target.checked ? [...draft.handoff_agent_ids, target.id] : draft.handoff_agent_ids.filter((id) => id !== target.id) })} />
              <span className="min-w-0 break-words">{target.name}</span>
            </label>)}
            {workflow.agents.length < 2 && <p className="py-6 text-center text-sm text-slate-500">{copy.noOtherAgents}</p>}
          </>}
        </fieldset>
        {readOnly && section === "agent" && <button type="button" onClick={() => setExpanded(true)} className="mt-2 text-sm text-sky-700">{copy.readFullInstructions}</button>}
      </div>
      {!readOnly && <div className="sticky bottom-0 z-10 flex items-center justify-between gap-2 rounded-b-2xl border-t border-slate-200 bg-white p-4">
        <button type="button" data-admin-write="true" disabled={!dirty || saving} onClick={onDiscard} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-40">{copy.discard}</button>
        <button type="submit" data-admin-write="true" disabled={!dirty || saving || stale || !validModel || !draft.name.trim() || !draft.model.trim() || !draft.instructions.trim()}
          className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-40"><Save className="h-4 w-4" />{saving ? copy.saveAgentProgress : editor.kind === "new" ? copy.createAgent : copy.saveAgent}</button>
      </div>}
      {expanded && <div role="dialog" aria-modal="true" aria-labelledby="workflow-instructions-title" className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/40 p-4">
        <div className="flex h-[85vh] w-full max-w-5xl flex-col gap-4 rounded-2xl bg-white p-5 shadow-xl">
          <div className="flex items-center justify-between gap-4"><h2 id="workflow-instructions-title" className="truncate text-lg font-semibold">{agent?.name || copy.newAgent} · {copy.instructions}</h2>
            <button id="workflow-instructions-close" type="button" aria-label={copy.closeInstructions} onClick={() => setExpanded(false)} className="rounded p-2 hover:bg-slate-100"><X className="h-5 w-5" /></button></div>
          {instructionsEditor(true)}
        </div>
      </div>}
    </form>
  );
}
