export interface WorkflowAgent {
  id: number;
  name: string;
  instructions: string;
  model: string;
  llm_provider_id: number | null;
  tool_ids: number[];
  handoff_agent_ids: number[];
  shared: boolean;
  updated_at: string | null;
}

export interface WorkflowTool {
  id: number;
  name: string;
  type: string;
}

export interface TeamWorkflow {
  team_id: number;
  team_name: string;
  default_agent_model?: string;
  can_edit: boolean;
  fallback_agent_id: number | null;
  agents: WorkflowAgent[];
  tools: WorkflowTool[];
  providers: { id: number; name: string }[];
}

export type WorkflowAgentDraft = Pick<WorkflowAgent,
  "name" | "instructions" | "model" | "llm_provider_id" | "tool_ids" | "handoff_agent_ids"
> & { is_fallback: boolean; expected_updated_at: string | null; expected_fallback_agent_id: number | null };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function isNullableId(value: unknown): value is number | null {
  return value === null || isId(value);
}

function isIds(value: unknown): value is number[] {
  return Array.isArray(value) && value.every(isId);
}

function isTimestamp(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isAgent(value: unknown): value is WorkflowAgent {
  return isRecord(value) && isId(value.id) && typeof value.name === "string" &&
    typeof value.instructions === "string" && typeof value.model === "string" &&
    isNullableId(value.llm_provider_id) && isIds(value.tool_ids) && isIds(value.handoff_agent_ids) &&
    typeof value.shared === "boolean" && isTimestamp(value.updated_at);
}

function isNamedId(value: unknown): value is { id: number; name: string } {
  return isRecord(value) && isId(value.id) && typeof value.name === "string";
}

function isTool(value: unknown): value is WorkflowTool {
  return isRecord(value) && isNamedId(value) && "type" in value && typeof value.type === "string";
}

export function parseTeamWorkflow(value: unknown): TeamWorkflow {
  if (!isRecord(value) || !isId(value.team_id) || typeof value.team_name !== "string" ||
    (value.default_agent_model !== undefined && typeof value.default_agent_model !== "string") ||
    typeof value.can_edit !== "boolean" || !isNullableId(value.fallback_agent_id) ||
    !Array.isArray(value.agents) || !value.agents.every(isAgent) ||
    !Array.isArray(value.tools) || !value.tools.every(isTool) ||
    !Array.isArray(value.providers) || !value.providers.every(isNamedId)) {
    throw new Error("Invalid workflow response. Reload to try again.");
  }
  return {
    team_id: value.team_id, team_name: value.team_name, can_edit: value.can_edit,
    default_agent_model: typeof value.default_agent_model === "string" ? value.default_agent_model.trim() : "",
    fallback_agent_id: value.fallback_agent_id, agents: value.agents,
    tools: value.tools, providers: value.providers,
  };
}

export function createAgentDraft(agent: WorkflowAgent, fallbackId: number | null): WorkflowAgentDraft {
  return {
    name: agent.name, instructions: agent.instructions, model: agent.model,
    llm_provider_id: agent.llm_provider_id, tool_ids: [...agent.tool_ids],
    handoff_agent_ids: [...agent.handoff_agent_ids], is_fallback: agent.id === fallbackId,
    expected_updated_at: agent.updated_at,
    expected_fallback_agent_id: fallbackId,
  };
}

export function isWorkflowAgentDraft(value: unknown): value is WorkflowAgentDraft {
  return isRecord(value) && typeof value.name === "string" && typeof value.instructions === "string" &&
    typeof value.model === "string" && isNullableId(value.llm_provider_id) &&
    isIds(value.tool_ids) && isIds(value.handoff_agent_ids) && typeof value.is_fallback === "boolean" &&
    isTimestamp(value.expected_updated_at) && isNullableId(value.expected_fallback_agent_id);
}

export function restoreWorkflowDrafts(raw: string | null, workflow: TeamWorkflow): Record<number, WorkflowAgentDraft> {
  const drafts: Record<number, WorkflowAgentDraft> = {};
  if (!raw) return drafts;
  try {
    const saved: unknown = JSON.parse(raw);
    if (!Array.isArray(saved)) return drafts;
    for (const item of saved) {
      if (!isRecord(item) || !isId(item.agent_id) || !isWorkflowAgentDraft(item.draft)) continue;
      const agent = workflow.agents.find((agent) => agent.id === item.agent_id);
      if (agent && !agent.shared && workflow.can_edit) drafts[agent.id] = item.draft;
    }
  } catch { return drafts; }
  return drafts;
}

export function isKnowledgeTool(tool: WorkflowTool): boolean {
  return tool.type === "okf_knowledge_graph" || tool.type === "gemini_file_search";
}

export async function workflowRequest(path: string, init?: RequestInit): Promise<unknown> {
  const { getApiBaseUrl } = await import("@/lib/api");
  const response = await fetch(`${getApiBaseUrl()}/api/admin${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("adminToken")}`, ...init?.headers },
    cache: "no-store",
  });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(data) && typeof data.detail === "string" ? data.detail : "Request failed. Try again.";
    throw new Error(detail);
  }
  return data;
}
