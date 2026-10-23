export type CreatedTool = { tool_id: number; name: string; type: string };
export type ToolCreationContext = { kind: "workflow"; teamId: number } | { kind: "tools-page"; teamId: number | null; assignAgentId: number | null };
type ToolPayload = { name: string; config: object; icon: string; visibility: string };

export function parseCreatedTool(value: unknown): number {
  if (!value || typeof value !== "object" || !("tool_id" in value) || typeof value.tool_id !== "number" || !Number.isSafeInteger(value.tool_id) || value.tool_id <= 0 || ("success" in value && value.success !== true)) throw new Error("The server did not confirm a valid tool ID. Retry to check the creation result.");
  return value.tool_id;
}

export function toolCreationRequest(context: ToolCreationContext, payload: ToolPayload, requestId: string) {
  if (context.kind === "workflow") return {
    path: `/api/admin/team-agents/${context.teamId}/workflow/tools`,
    body: { ...payload, visibility: "team", request_id: requestId },
  };
  return {
    path: `/api/admin/tools${context.teamId ? `?team_agent_id=${context.teamId}` : ""}`,
    body: { ...payload, assign_agent_id: context.assignAgentId },
  };
}
