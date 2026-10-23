export const DEFAULT_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"];

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
