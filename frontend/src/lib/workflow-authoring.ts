import { createAgentDraft, isWorkflowAgentDraft, type TeamWorkflow, type WorkflowAgent, type WorkflowAgentDraft, type WorkflowTool } from "@/lib/team-workflow";

export type WorkflowTarget = { kind: "agent"; agentId: number } | { kind: "new"; requestId: string };
export type WorkflowSelection = WorkflowTarget | { kind: "none" };
export type WorkflowNewAgent = { requestId: string; draft: WorkflowAgentDraft };
export type WorkflowEditor = { kind: "existing"; agent: WorkflowAgent; draft: WorkflowAgentDraft } |
  { kind: "new"; draft: WorkflowAgentDraft };

export interface WorkflowReadyState {
  status: "ready";
  workflow: TeamWorkflow;
  selection: WorkflowSelection;
  drafts: Record<number, WorkflowAgentDraft>;
  newAgent: WorkflowNewAgent | null;
}

export function createNewWorkflowAgent(workflow: TeamWorkflow): WorkflowNewAgent {
  return { requestId: crypto.randomUUID(), draft: {
    name: "", instructions: "", model: "", llm_provider_id: null,
    tool_ids: workflow.tools.filter((tool) => tool.name === "DateTimeTool").map((tool) => tool.id),
    handoff_agent_ids: [], is_fallback: workflow.agents.length === 0,
    expected_updated_at: null, expected_fallback_agent_id: workflow.fallback_agent_id,
  } };
}

export function restoreNewWorkflowAgent(raw: string | null, canEdit: boolean): WorkflowNewAgent | null {
  if (!raw || !canEdit) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || !("requestId" in value) || typeof value.requestId !== "string" ||
      !/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i.test(value.requestId) || !("draft" in value) || !isWorkflowAgentDraft(value.draft)) return null;
    return { requestId: value.requestId, draft: value.draft };
  } catch { return null; }
}

export function getWorkflowEditor(state: WorkflowReadyState): WorkflowEditor | null {
  if (state.selection.kind === "none") return null;
  if (state.selection.kind === "new") return state.newAgent && state.newAgent.requestId === state.selection.requestId ? { kind: "new", draft: state.newAgent.draft } : null;
  const id = state.selection.agentId;
  const agent = state.workflow.agents.find((agent) => agent.id === id);
  return agent ? { kind: "existing", agent, draft: state.drafts[id] ?? createAgentDraft(agent, state.workflow.fallback_agent_id) } : null;
}

export function changeWorkflowDraft(state: WorkflowReadyState, target: WorkflowTarget,
  update: (draft: WorkflowAgentDraft) => WorkflowAgentDraft): WorkflowReadyState {
  if (!state.workflow.can_edit) return state;
  if (target.kind === "new") return state.newAgent && state.newAgent.requestId === target.requestId ? { ...state, newAgent: { ...state.newAgent, draft: update(state.newAgent.draft) } } : state;
  const agent = state.workflow.agents.find((agent) => agent.id === target.agentId);
  if (!agent || agent.shared) return state;
  const original = createAgentDraft(agent, state.workflow.fallback_agent_id);
  const draft = update(state.drafts[agent.id] ?? original);
  const drafts = { ...state.drafts };
  if (JSON.stringify(draft) === JSON.stringify(original)) delete drafts[agent.id];
  else drafts[agent.id] = draft;
  return { ...state, drafts };
}

export function projectWorkflowAgents(state: WorkflowReadyState): WorkflowAgent[] {
  return state.workflow.agents.map((agent) => {
    const draft = state.drafts[agent.id];
    return draft ? { ...agent, name: draft.name, instructions: draft.instructions, model: draft.model,
      llm_provider_id: draft.llm_provider_id, tool_ids: draft.tool_ids, handoff_agent_ids: draft.handoff_agent_ids } : agent;
  });
}

export interface HandoffChange { sourceId: number; targetId: number; connected: boolean }

export function canChangeWorkflowHandoff(state: WorkflowReadyState, change: HandoffChange): boolean {
  const source = state.workflow.agents.find((agent) => agent.id === change.sourceId);
  if (!state.workflow.can_edit || !source || source.shared || change.sourceId === change.targetId ||
    !state.workflow.agents.some((agent) => agent.id === change.targetId)) return false;
  const ids = state.drafts[source.id]?.handoff_agent_ids ?? source.handoff_agent_ids;
  return change.connected ? !ids.includes(change.targetId) : ids.includes(change.targetId);
}

export function stageWorkflowHandoff(state: WorkflowReadyState, change: HandoffChange): WorkflowReadyState {
  if (!canChangeWorkflowHandoff(state, change)) return state;
  const updated = changeWorkflowDraft(state, { kind: "agent", agentId: change.sourceId }, (draft) => ({ ...draft,
    handoff_agent_ids: change.connected ? [...draft.handoff_agent_ids, change.targetId] : draft.handoff_agent_ids.filter((id) => id !== change.targetId),
  }));
  return { ...updated, selection: { kind: "agent", agentId: change.sourceId } };
}

export function addCreatedWorkflowTool(state: WorkflowReadyState, target: WorkflowTarget | null, tool: WorkflowTool): WorkflowReadyState {
  const tools = state.workflow.tools.some((current) => current.id === tool.id) ? state.workflow.tools : [...state.workflow.tools, tool];
  const updated = { ...state, workflow: { ...state.workflow, tools } };
  return target ? changeWorkflowDraft(updated, target, (draft) => ({ ...draft,
    tool_ids: Array.from(new Set([...draft.tool_ids, tool.id])),
  })) : updated;
}

export function parseCreatedAgentId(value: unknown): number {
  if (typeof value !== "object" || value === null || !("agent_id" in value) || typeof value.agent_id !== "number" ||
    !Number.isSafeInteger(value.agent_id) || value.agent_id < 1) throw new Error("Agent creation response is incomplete. Retry with the same draft.");
  return value.agent_id;
}

export function reconcileWorkflow(state: WorkflowReadyState, workflow: TeamWorkflow, deletedToolId?: number): WorkflowReadyState {
  const drafts: Record<number, WorkflowAgentDraft> = {};
  for (const agent of workflow.agents) {
    const draft = state.drafts[agent.id];
    if (!draft || agent.shared || !workflow.can_edit) continue;
    const oldFallback = agent.id === state.workflow.fallback_agent_id;
    const fallbackDrafted = draft.is_fallback !== oldFallback;
    drafts[agent.id] = { ...draft,
      tool_ids: draft.tool_ids.filter((id) => id !== deletedToolId),
      handoff_agent_ids: draft.handoff_agent_ids.filter((id) => workflow.agents.some((member) => member.id === id)),
      ...(fallbackDrafted ? {} : { is_fallback: agent.id === workflow.fallback_agent_id, expected_fallback_agent_id: workflow.fallback_agent_id }),
    };
  }
  const selection = state.selection.kind === "agent" && !workflow.agents.some((agent) => state.selection.kind === "agent" && agent.id === state.selection.agentId)
    ? workflow.agents[0] ? { kind: "agent" as const, agentId: workflow.agents[0].id } : { kind: "none" as const } : state.selection;
  return { ...state, workflow, drafts, selection,
    newAgent: state.newAgent ? { ...state.newAgent, draft: { ...state.newAgent.draft,
      tool_ids: state.newAgent.draft.tool_ids.filter((id) => id !== deletedToolId),
      handoff_agent_ids: state.newAgent.draft.handoff_agent_ids.filter((id) => workflow.agents.some((member) => member.id === id)),
      ...(state.newAgent.draft.is_fallback !== (state.workflow.agents.length === 0) ? {} : { is_fallback: workflow.agents.length === 0, expected_fallback_agent_id: workflow.fallback_agent_id }),
    } } : null };
}
