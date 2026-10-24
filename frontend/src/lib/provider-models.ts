export interface AgentModelDefaults {
  default_agent_model: string;
  agent_models: string[];
}

export function parseAgentModelDefaults(value: unknown): AgentModelDefaults {
  if (typeof value !== "object" || value === null ||
    !("default_agent_model" in value) || typeof value.default_agent_model !== "string" || !value.default_agent_model.trim() ||
    !("agent_models" in value) || !Array.isArray(value.agent_models) ||
    !value.agent_models.every((item: unknown) => typeof item === "string" && !!item.trim())) {
    throw new Error("Invalid model defaults");
  }
  const defaultModel = value.default_agent_model.trim();
  return { default_agent_model: defaultModel, agent_models: Array.from(new Set([defaultModel, ...value.agent_models.map((item: string) => item.trim())])) };
}

export function parseModelIds(data: unknown, registered: boolean): string[] {
  if (!Array.isArray(data)) throw new Error("Invalid model list");
  return data.flatMap((item: unknown) => {
    if (!registered && typeof item === "string") return item.trim() ? [item.trim()] : [];
    if (typeof item !== "object" || item === null) return [];
    if (registered && (!("enabled" in item) || item.enabled !== true ||
      !("capabilities" in item) || !Array.isArray(item.capabilities) || !item.capabilities.includes("text"))) return [];
    const id = registered ? ("model_id" in item ? item.model_id : null) : ("id" in item ? item.id : null);
    return typeof id === "string" && id.trim() ? [id.trim()] : [];
  });
}
