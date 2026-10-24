"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, BookOpen, Bot, List, Plus, RefreshCw, Search, Star, Wrench, Users, Library, MessageSquare, Network, Radio } from "lucide-react";
import { useTeam } from "@/lib/team-context";
import { parseTeamWorkflow, restoreWorkflowDrafts, workflowRequest, type WorkflowAgentDraft } from "@/lib/team-workflow";
import { addCreatedWorkflowTool, changeWorkflowDraft, createNewWorkflowAgent, getWorkflowEditor, parseCreatedAgentId, projectWorkflowAgents, reconcileWorkflow, restoreNewWorkflowAgent, stageWorkflowHandoff, type HandoffChange, type WorkflowReadyState, type WorkflowTarget } from "@/lib/workflow-authoring";
import WorkflowAgentInspector from "@/components/WorkflowAgentInspector";
import WorkflowToolModal from "@/components/WorkflowToolModal";
import WorkflowMembersPanel from "@/components/WorkflowMembersPanel";
import WorkflowProviderModal from "@/components/WorkflowProviderModal";
import WorkflowCapabilitiesPanel, { type WorkflowResourceMutation } from "@/components/WorkflowCapabilitiesPanel";
import WorkflowAgentTestPanel from "@/components/WorkflowAgentTestPanel";
import WorkflowPreviewChat from "@/components/WorkflowPreviewChat";
import WorkflowChannels from "@/components/WorkflowChannels";
import CreateOKFBundleModal from "@/components/CreateOKFBundleModal";

const AgentFlowGraph = dynamic(() => import("@/components/AgentFlowGraph"), { ssr: false,
  loading: () => <div role="status" className="grid min-h-80 place-items-center rounded-2xl border border-slate-200 text-sm text-slate-500">Loading diagram…</div> });

type WorkspaceState = { status: "loading" } | { status: "error"; message: string } | WorkflowReadyState;
type SaveReceipt = { kind: "membership" } | { kind: "resource"; deletedToolId?: number } | { kind: "deleted"; agentId: number } | { kind: "updated"; agentId: number } | { kind: "created"; agentId: number; requestId: string };
type SaveState = { status: "idle" } | { status: "saving" } | { status: "saved"; message: string } |
  { status: "error"; message: string } | { status: "refresh-error"; message: string; receipt: SaveReceipt };
type ResourceEditor = { kind: "closed" } | { kind: "tool" | "knowledge"; target: WorkflowTarget | null };

function importStorageKey(teamId: number, target: WorkflowTarget | null) {
  return `workflow-import:${teamId}:${target?.kind === "agent" ? target.agentId : target?.kind === "new" ? `new-${target.requestId}` : "library"}`;
}

function restoreKnowledgeEditor(raw: string | null, state: WorkflowReadyState): ResourceEditor {
  if (!raw || !state.workflow.can_edit) return { kind: "closed" };
  try {
    const value: unknown = JSON.parse(raw);
    if (value === null) return { kind: "knowledge", target: null };
    if (typeof value !== "object" || !("kind" in value)) return { kind: "closed" };
    if (value.kind === "new" && "requestId" in value && state.newAgent && state.newAgent.requestId === value.requestId) return { kind: "knowledge", target: { kind: "new", requestId: state.newAgent.requestId } };
    if (value.kind === "agent" && "agentId" in value && typeof value.agentId === "number" && state.workflow.agents.some((agent) => agent.id === value.agentId && !agent.shared)) {
      return { kind: "knowledge", target: { kind: "agent", agentId: value.agentId } };
    }
  } catch { return { kind: "closed" }; }
  return { kind: "closed" };
}

export default function TeamWorkflowWorkspace({ teamId }: { teamId: number }) {
  const router = useRouter();
  const { setSelectedTeamId, refreshTeams } = useTeam();
  const [state, setState] = useState<WorkspaceState>({ status: "loading" });
  const [saveState, setSaveState] = useState<SaveState>({ status: "idle" });
  const [resourceEditor, setResourceEditor] = useState<ResourceEditor>({ kind: "closed" });
  const [panel, setPanel] = useState<"closed" | "members" | "library">("closed");
  const [testing, setTesting] = useState<{ id: number; name: string } | null>(null);
  const [view, setView] = useState<"design" | "chat" | "channels">("design");
  const [channelsVisited, setChannelsVisited] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [previewTarget, setPreviewTarget] = useState<number | null>(null);
  const [providerTarget, setProviderTarget] = useState<WorkflowTarget | null>(null);
  const [superAdmin, setSuperAdmin] = useState(false);
  const [query, setQuery] = useState("");
  const [showList, setShowList] = useState(false);
  const [storageError, setStorageError] = useState(false);
  const operation = useRef(false);
  const focusNewAgent = useRef(false);
  const storageKey = `team-workflow-drafts:${teamId}`;
  const newStorageKey = `team-workflow-new:${teamId}`;
  const knowledgeContextKey = `workflow-import-target:${teamId}`;
  const dirtyCount = state.status === "ready" ? Object.keys(state.drafts).length + (state.newAgent ? 1 : 0) : 0;
  const locked = saveState.status === "saving" || saveState.status === "refresh-error";

  const loadWorkflow = useCallback(async (signal?: AbortSignal) => {
    const workflow = parseTeamWorkflow(await workflowRequest(`/team-agents/${teamId}/workflow`, { signal }));
    if (workflow.team_id !== teamId) throw new Error("Workflow belongs to a different team.");
    return workflow;
  }, [teamId]);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    void loadWorkflow(controller.signal).then((workflow) => {
      if (controller.signal.aborted) return;
      let raw: string | null = null;
      let newRaw: string | null = null;
      let importRaw: string | null = null;
      try { raw = sessionStorage.getItem(storageKey); newRaw = sessionStorage.getItem(newStorageKey); importRaw = sessionStorage.getItem(knowledgeContextKey); }
      catch { setStorageError(true); }
      const newAgent = restoreNewWorkflowAgent(newRaw, workflow.can_edit);
      const ready: WorkflowReadyState = { status: "ready", workflow,
        selection: newAgent ? { kind: "new", requestId: newAgent.requestId } : workflow.agents[0] ? { kind: "agent", agentId: workflow.agents[0].id } : { kind: "none" },
        drafts: restoreWorkflowDrafts(raw, workflow), newAgent };
      setState(ready);
      const editor = restoreKnowledgeEditor(importRaw, ready);
      try { if (editor.kind === "knowledge" && sessionStorage.getItem(importStorageKey(teamId, editor.target))) setResourceEditor(editor); }
      catch { setStorageError(true); }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ status: "error", message: error instanceof Error ? error.message : "Unable to load workflow." });
    });
    return () => controller.abort();
  }, [loadWorkflow, storageKey, newStorageKey, knowledgeContextKey, teamId]);

  useEffect(() => {
    const controller = new AbortController();
    void workflowRequest("/auth/me", { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted && data && typeof data === "object" && "is_super_admin" in data) setSuperAdmin(data.is_super_admin === true);
    }).catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => { setSelectedTeamId(teamId); }, [teamId, setSelectedTeamId]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 1023px)");
    const update = () => { if (media.matches) setShowList(true); };
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (state.status !== "ready") return;
    try {
      if (Object.keys(state.drafts).length) sessionStorage.setItem(storageKey,
        JSON.stringify(Object.entries(state.drafts).map(([id, draft]) => ({ agent_id: Number(id), draft }))));
      else sessionStorage.removeItem(storageKey);
      if (state.newAgent) sessionStorage.setItem(newStorageKey, JSON.stringify(state.newAgent));
      else sessionStorage.removeItem(newStorageKey);
    } catch { setStorageError(true); }
  }, [state, storageKey, newStorageKey]);

  useEffect(() => {
    if (!dirtyCount && resourceEditor.kind === "closed") return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const beforeNavigate = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("a[href]") && !window.confirm("Leave Workflow with unsaved changes? Agent drafts stay in this tab.")) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload); document.addEventListener("click", beforeNavigate, true);
    return () => { window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", beforeNavigate, true); };
  }, [dirtyCount, resourceEditor.kind]);

  useEffect(() => {
    if (!focusNewAgent.current || state.status !== "ready" || state.selection.kind !== "new") return;
    focusNewAgent.current = false;
    const inspector = document.getElementById("workflow-agent-inspector");
    const name = document.getElementById("workflow-agent-name");
    (name ?? inspector)?.focus({ preventScroll: true });
    if (typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1023px)").matches) {
      inspector?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [state]);

  const selectAgent = useCallback((id: number) => {
    if (operation.current || locked) return;
    setState((previous) => previous.status === "ready" ? { ...previous, selection: { kind: "agent", agentId: id } } : previous);
    setSaveState({ status: "idle" });
    if (typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1023px)").matches) {
      document.getElementById("workflow-agent-inspector")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [locked]);

  const applySavedWorkflow = (workflow: WorkflowReadyState["workflow"], receipt: SaveReceipt) => {
    setState((previous) => {
      if (previous.status !== "ready") return previous;
      const next = reconcileWorkflow(previous, workflow, receipt.kind === "resource" ? receipt.deletedToolId : undefined);
      if (receipt.kind === "membership" || receipt.kind === "resource" || receipt.kind === "deleted") return next;
      const drafts = { ...next.drafts }; delete drafts[receipt.agentId];
      return { ...next, drafts, selection: { kind: "agent", agentId: receipt.agentId },
        newAgent: receipt.kind === "created" && previous.newAgent?.requestId === receipt.requestId ? null : previous.newAgent };
    });
    setSaveState({ status: "saved", message: receipt.kind === "created" ? "Agent created" : receipt.kind === "deleted" ? "Agent deleted" : receipt.kind === "membership" ? "Members saved" : receipt.kind === "resource" ? "Resource saved" : "Agent saved" });
    void refreshTeams();
  };

  const commitChange = async (path: string, method: string, body: object, receipt: SaveReceipt) => {
    if (operation.current || locked) return;
    operation.current = true; setSaveState({ status: "saving" }); let committed = false;
    try {
      await workflowRequest(path, { method, body: JSON.stringify(body) }); committed = true;
      applySavedWorkflow(await loadWorkflow(), receipt); setPanel("closed");
    } catch (failure: unknown) {
      const message = failure instanceof Error ? failure.message : "Unable to save changes.";
      setSaveState(committed ? { status: "refresh-error", message: "Changes saved. Refresh workflow before continuing.", receipt } : { status: "error", message });
      throw failure;
    } finally { operation.current = false; }
  };
  const resourceMutated = async (result: WorkflowResourceMutation) => {
    const receipt: SaveReceipt = { kind: "resource", deletedToolId: result.kind === "deleted" ? result.toolId : undefined };
    if (operation.current) throw Error("Another operation is in progress.");
    operation.current = true; setSaveState({ status: "saving" });
    try { applySavedWorkflow(await loadWorkflow(), receipt); }
    catch (failure) { setSaveState({ status: "refresh-error", message: "Resource saved. Refresh workflow before continuing.", receipt }); throw failure; }
    finally { operation.current = false; }
  };

  const saveAgent = async () => {
    if (state.status !== "ready" || operation.current || locked) return;
    const editor = getWorkflowEditor(state);
    if (!editor || !state.workflow.can_edit || editor.kind === "existing" && editor.agent.shared) return;
    if (!editor.draft.name.trim() || !editor.draft.model.trim() || !editor.draft.instructions.trim()) return;
    if (editor.kind === "existing" && !window.confirm("Save Agent changes? Saved settings affect customer channels using this Agent. Private preview does not require saving.")) return;
    operation.current = true; setSaveState({ status: "saving" });
    let receipt: SaveReceipt | null = null;
    try {
      const body = { ...editor.draft, name: editor.draft.name.trim(), model: editor.draft.model.trim() };
      if (editor.kind === "new" && state.newAgent) {
        const requestId = state.newAgent.requestId;
        const agentId = parseCreatedAgentId(await workflowRequest(`/team-agents/${teamId}/workflow/agents`, { method: "POST", body: JSON.stringify({ ...body, request_id: requestId }) }));
        receipt = { kind: "created", agentId, requestId };
      } else if (editor.kind === "existing") {
        await workflowRequest(`/team-agents/${teamId}/workflow/agents/${editor.agent.id}`, { method: "PUT", body: JSON.stringify(body) });
        receipt = { kind: "updated", agentId: editor.agent.id };
      }
      if (receipt) applySavedWorkflow(await loadWorkflow(), receipt);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unable to save agent.";
      setSaveState(receipt ? { status: "refresh-error", message: "Agent saved, but the workflow could not be refreshed. Refresh before continuing.", receipt } : { status: "error", message });
    } finally { operation.current = false; }
  };

  const refreshAfterSave = async (receipt: SaveReceipt) => {
    if (operation.current) return;
    operation.current = true; setSaveState({ status: "saving" });
    try { applySavedWorkflow(await loadWorkflow(), receipt); if (receipt.kind === "membership" || receipt.kind === "deleted") setPanel("closed"); }
    catch { setSaveState({ status: "refresh-error", message: "Changes saved. Workflow refresh failed. Try again.", receipt }); }
    finally { operation.current = false; }
  };

  const openResource = (kind: "tool" | "knowledge", target: WorkflowTarget | null) => {
    if (locked || operation.current || state.status !== "ready" || !state.workflow.can_edit) return;
    if (kind === "knowledge") {
      try { sessionStorage.setItem(knowledgeContextKey, JSON.stringify(target)); } catch { setStorageError(true); }
    }
    setResourceEditor({ kind, target });
  };
  const closeResource = () => {
    setResourceEditor({ kind: "closed" });
    try { sessionStorage.removeItem(knowledgeContextKey); } catch { setStorageError(true); }
  };
  const resourceCreated = (tool: { tool_id: number; name: string; type: string }, close: boolean) => {
    if (resourceEditor.kind === "closed") return;
    const target = resourceEditor.target;
    setState((previous) => previous.status === "ready" ? addCreatedWorkflowTool(previous, target, { id: tool.tool_id, name: tool.name, type: tool.type }) : previous);
    setSaveState({ status: "saved", message: "Resource created" });
    if (close) closeResource();
  };
  const handoffChanged = (change: HandoffChange) => {
    if (locked || operation.current || resourceEditor.kind !== "closed") return;
    setState((previous) => previous.status === "ready" ? stageWorkflowHandoff(previous, change) : previous);
    setSaveState({ status: "idle" });
  };

  if (state.status === "loading") return <div role="status" className="py-20 text-center text-sm text-slate-500">Loading workflow…</div>;
  if (state.status === "error") return <div role="alert" className="space-y-4 rounded-xl border border-red-200 bg-red-50 p-6 text-red-900"><p>{state.message}</p><button type="button" onClick={() => window.location.reload()} className="rounded-lg border border-red-300 px-3 py-2 text-sm">Retry</button></div>;

  const { workflow } = state;
  const editor = getWorkflowEditor(state);
  const target: WorkflowTarget | null = state.selection.kind === "none" ? null : state.selection;
  const resourceTarget = editor && !(editor.kind === "existing" && editor.agent.shared) ? target : null;
  const addAgent = () => {
    if (locked || operation.current || !workflow.can_edit || resourceEditor.kind !== "closed") return;
    focusNewAgent.current = true;
    setState((previous) => {
      if (previous.status !== "ready") return previous;
      const newAgent = previous.newAgent ?? createNewWorkflowAgent(previous.workflow);
      return { ...previous, newAgent, selection: { kind: "new", requestId: newAgent.requestId } };
    });
    setSaveState({ status: "idle" });
  };
  const changeDraft = (draft: WorkflowAgentDraft) => {
    if (!target || locked || operation.current) return;
    setState((previous) => previous.status === "ready" ? changeWorkflowDraft(previous, target, () => draft) : previous);
    setSaveState({ status: "idle" });
  };
  const discard = () => {
    if (!target || locked || operation.current) return;
    setState((previous) => {
      if (previous.status !== "ready") return previous;
      if (target.kind === "new") return { ...previous, newAgent: null, selection: workflow.agents[0] ? { kind: "agent", agentId: workflow.agents[0].id } : { kind: "none" } };
      const drafts = { ...previous.drafts }; delete drafts[target.agentId]; return { ...previous, drafts };
    });
    setSaveState({ status: "idle" });
  };
  const toolbarButton = "inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-40";

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3"><button type="button" aria-label="Back to Team Agents" title="Back to Team Agents" disabled={locked}
        onClick={() => { if (!dirtyCount || window.confirm("Leave Workflow with unsaved changes? Agent drafts stay in this tab.")) router.push("/admin/teams"); }} className="shrink-0 rounded-lg border border-slate-200 p-2 text-slate-500 disabled:opacity-40"><ArrowLeft className="h-5 w-5" /></button>
        <div className="min-w-0"><div className="text-xs text-slate-500">Workflow</div><h1 className="break-words text-2xl font-semibold text-slate-900">{workflow.team_name}</h1></div></div>
      <div className="flex flex-wrap items-center gap-2"><span role="status" className="mr-2 text-xs text-slate-500">{dirtyCount ? `${dirtyCount} unsaved agent${dirtyCount === 1 ? "" : "s"}` : saveState.status === "saved" ? saveState.message : "All changes saved"}</span>
        {view === "design" && <>
        <button type="button" aria-expanded={manageOpen} onClick={() => setManageOpen(!manageOpen)} className={`${toolbarButton} lg:hidden`}>Manage</button>
        <div className={`${manageOpen ? "flex" : "hidden lg:flex"} flex-wrap items-center gap-2`}>
        <button type="button" onClick={() => setShowList(!showList)} aria-pressed={showList} className={toolbarButton}><List className="h-4 w-4" />Agents</button>
        <button type="button" disabled={locked} onClick={() => setPanel(panel === "library" ? "closed" : "library")} className={toolbarButton}><Library className="h-4 w-4" />Library</button>
        {workflow.can_edit && <><button type="button" disabled={locked} onClick={() => setPanel(panel === "members" ? "closed" : "members")} className={toolbarButton}><Users className="h-4 w-4" />Members</button><button type="button" disabled={locked} onClick={() => openResource("tool", resourceTarget)} className={toolbarButton}><Wrench className="h-4 w-4" />Tool</button>
          <button type="button" disabled={locked} onClick={() => openResource("knowledge", resourceTarget)} className={toolbarButton}><BookOpen className="h-4 w-4" />Knowledge</button>
          <button type="button" onClick={addAgent} disabled={locked || resourceEditor.kind !== "closed"} aria-controls="workflow-agent-inspector" className={toolbarButton}><Plus className="h-4 w-4" />{state.newAgent ? "New agent" : "Agent"}</button></>}
        </div>
        </>}
        {view !== "chat" && <button type="button" disabled={locked || !workflow.agents.length || !workflow.can_edit} onClick={() => { setPreviewTarget(null); setView("chat"); setPanel("closed"); }} className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"><MessageSquare className="h-4 w-4" />{Object.keys(state.drafts).length ? "Try draft" : "Chat with team"}</button>}
      </div>
    </div>
    <nav aria-label="Team workspace" className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {([{ id: "design", label: "Design", icon: Network }, { id: "chat", label: "Private chat", icon: MessageSquare }, { id: "channels", label: "Channels", icon: Radio }] satisfies { id: typeof view; label: string; icon: typeof Network }[]).map(({ id, label, icon: Icon }) => <button key={id} type="button" aria-current={view === id ? "page" : undefined} disabled={locked || id === "chat" && (!workflow.can_edit || !workflow.agents.length)} onClick={() => { setView(id); if (id === "channels") setChannelsVisited(true); setPanel("closed"); }} className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium disabled:opacity-40 ${view === id ? "border-sky-600 text-sky-700" : "border-transparent text-slate-500"}`}><Icon size={16} />{label}</button>)}
    </nav>
    {panel === "members" && <WorkflowMembersPanel workflow={workflow} busy={locked} onClose={() => setPanel("closed")} onSave={async (memberIds, fallbackId, expectedIds, expectedFallback) => {
      await commitChange(`/team-agents/${teamId}/workflow/members`, "PUT", { member_agent_ids: memberIds, fallback_agent_id: fallbackId, expected_member_agent_ids: expectedIds, expected_fallback_agent_id: expectedFallback }, { kind: "membership" });
    }} />}
    {panel === "library" && <WorkflowCapabilitiesPanel teamId={teamId} canEdit={workflow.can_edit && !locked} onClose={() => setPanel("closed")} onMutation={resourceMutated} />}
    {storageError && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Draft storage is unavailable. Save changes before leaving.</p>}
    {(saveState.status === "error" || saveState.status === "refresh-error") && <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800"><p>{saveState.message}</p>
      {saveState.status === "refresh-error" ? <button type="button" onClick={() => void refreshAfterSave(saveState.receipt)} className="inline-flex items-center gap-1 underline"><RefreshCw className="h-4 w-4" />Refresh workflow</button> :
        <button type="button" onClick={() => window.location.reload()} className="inline-flex items-center gap-1 underline"><RefreshCw className="h-4 w-4" />Reload saved settings</button>}</div>}
    <div hidden={view !== "design"}>
    {showList && <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3"><label className="mb-3 flex max-w-sm items-center gap-2 rounded-lg border border-slate-200 px-3 py-2"><Search className="h-4 w-4 text-slate-400" /><input aria-label="Search agents" value={query} onChange={(event) => setQuery(event.target.value)} className="min-w-0 flex-1 text-sm outline-none" /></label>
      <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto">{workflow.agents.filter((agent) => agent.name.toLowerCase().includes(query.toLowerCase())).map((agent) => <button key={agent.id} type="button" onClick={() => selectAgent(agent.id)} aria-pressed={state.selection.kind === "agent" && agent.id === state.selection.agentId} className={`${toolbarButton} max-w-full ${state.selection.kind === "agent" && agent.id === state.selection.agentId ? "border-sky-400 bg-sky-50 text-sky-800" : ""}`}><Bot className="h-4 w-4 shrink-0" /><span className="truncate">{state.drafts[agent.id]?.name || agent.name}</span>{agent.id === workflow.fallback_agent_id && <Star aria-label="Fallback" className="h-3.5 w-3.5 text-amber-600" />}{state.drafts[agent.id] && <span aria-label="Unsaved changes" className="h-2 w-2 rounded-full bg-amber-400" />}</button>)}
        {state.newAgent && <button type="button" onClick={addAgent} disabled={locked || resourceEditor.kind !== "closed"} aria-controls="workflow-agent-inspector" aria-pressed={state.selection.kind === "new"} className={toolbarButton}><Plus className="h-4 w-4" />{state.newAgent.draft.name || "New agent"}<span className="h-2 w-2 rounded-full bg-amber-400" /></button>}
        {!workflow.agents.some((agent) => agent.name.toLowerCase().includes(query.toLowerCase())) && !state.newAgent && <p className="text-sm text-slate-500">No agents found.</p>}</div></div>}
    {workflow.agents.length === 0 && !editor ? <div className="grid min-h-96 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><div><Bot className="mx-auto mb-3 h-10 w-10 text-slate-300" /><h2 className="text-lg font-semibold">No agents in this team</h2>{workflow.can_edit && <button type="button" onClick={addAgent} disabled={locked || resourceEditor.kind !== "closed"} aria-controls="workflow-agent-inspector" className="mt-4 min-h-11 rounded-lg bg-sky-600 px-4 py-2 text-sm text-white disabled:opacity-40">Create agent</button>}</div></div> :
      <div className="grid min-w-0 items-stretch gap-4 lg:h-[calc(100dvh-280px)] lg:min-h-[480px] lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
        <AgentFlowGraph agents={projectWorkflowAgents(state)} tools={workflow.tools} fallbackAgentId={workflow.fallback_agent_id} selectedAgentId={state.selection.kind === "agent" ? state.selection.agentId : null}
          onSelect={selectAgent} canEdit={workflow.can_edit} disabled={locked || resourceEditor.kind !== "closed"} pendingAgentIds={Object.keys(state.drafts).map(Number)} onHandoffChange={handoffChanged} onAddAgent={addAgent} hasNewAgentDraft={Boolean(state.newAgent)} />
        {editor && <div id="workflow-agent-inspector" tabIndex={-1} role="region" aria-label="Agent editor" className="min-h-0 min-w-0 scroll-mt-20"><WorkflowAgentInspector key={editor.kind === "new" ? "new" : editor.agent.id} workflow={workflow} editor={editor}
          dirty={editor.kind === "new" || Boolean(state.drafts[editor.agent.id])} saving={saveState.status === "saving"} locked={saveState.status === "refresh-error"}
          onSave={() => void saveAgent()} onDiscard={discard} onChange={changeDraft} onCreateTool={() => openResource("tool", target)} onCreateKnowledge={() => openResource("knowledge", target)}
          onTest={editor.kind === "existing" && workflow.can_edit ? () => { setPreviewTarget(editor.agent.id); setView("chat"); } : undefined}
          onCreateProvider={superAdmin && workflow.can_edit ? () => setProviderTarget(target) : undefined}
          onDelete={editor.kind === "existing" && !editor.agent.shared ? (replacementFallbackId) => {
            if (!window.confirm(`Permanently delete ${editor.agent.name}? This cannot be undone.`)) return;
            void commitChange(`/team-agents/${teamId}/workflow/agents/${editor.agent.id}`, "DELETE", { expected_updated_at: editor.agent.updated_at, expected_member_agent_ids: workflow.agents.map((agent) => agent.id), expected_fallback_agent_id: workflow.fallback_agent_id, replacement_fallback_agent_id: replacementFallbackId }, { kind: "deleted", agentId: editor.agent.id }).catch(() => {});
          } : undefined} /></div>}
      </div>}
    {editor?.kind === "existing" && <details className="mt-3 text-sm text-slate-500"><summary className="cursor-pointer">Advanced diagnostics</summary><button type="button" aria-label="Test saved agent" disabled={locked} onClick={() => setTesting({ id: editor.agent.id, name: editor.agent.name })} className="mt-2 rounded-lg border px-3 py-2">Test saved agent</button></details>}
    </div>
    {view === "chat" && state.newAgent && <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Save the new Agent to include it in preview.</p>}
    {workflow.can_edit && <WorkflowPreviewChat key={`preview-${teamId}`} teamId={teamId} workflow={workflow} drafts={state.drafts} targetAgentId={previewTarget} onTargetChange={setPreviewTarget} visible={view === "chat"}
      onEditAgent={id => { selectAgent(id); setView("design"); }} onOpenKnowledge={() => setPanel("library")} />}
    {channelsVisited && <div className={view === "channels" ? "block" : "hidden"}><WorkflowChannels key={`channels-${teamId}`} teamId={teamId} teamName={workflow.team_name} canEdit={workflow.can_edit} hasDrafts={dirtyCount > 0} /></div>}
    {testing && <WorkflowAgentTestPanel teamId={teamId} agent={testing} hasUnsavedChanges={Boolean(state.drafts[testing.id])} onClose={() => setTesting(null)} />}
    {providerTarget && <WorkflowProviderModal onClose={() => setProviderTarget(null)} onCreated={async (providerId) => {
      const data = await workflowRequest("/llm-providers");
      if (!Array.isArray(data) || !data.every((provider: unknown) => provider && typeof provider === "object" && "id" in provider && typeof provider.id === "number" && "name" in provider && typeof provider.name === "string")) throw Error("Unable to refresh providers.");
      const providers = data.map((provider) => ({ id: provider.id as number, name: provider.name as string }));
      if (!providers.some((provider) => provider.id === providerId)) throw Error("Created provider is not available yet.");
      setState((previous) => previous.status === "ready" ? changeWorkflowDraft({ ...previous, workflow: { ...previous.workflow, providers } }, providerTarget, (draft) => ({ ...draft, llm_provider_id: providerId, model: "" })) : previous);
      setProviderTarget(null);
    }} />}
    {resourceEditor.kind === "tool" && <WorkflowToolModal teamId={teamId} onClose={closeResource} onCreated={(result) => resourceCreated(result, true)} />}
    {resourceEditor.kind === "knowledge" && <CreateOKFBundleModal teamAgentId={teamId} assignAgentId={null} teamName={workflow.team_name}
      jobStorageKey={importStorageKey(teamId, resourceEditor.target)} onClose={closeResource}
      onSuccess={(result) => resourceCreated({ tool_id: result.tool_id, name: result.display_name, type: "okf_knowledge_graph" }, false)} />}
  </div>;
}
