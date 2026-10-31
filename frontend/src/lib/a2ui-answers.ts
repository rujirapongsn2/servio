import catalog from "./a2ui-answers.catalog.json";

export const ANSWER_CATALOG = catalog.catalogId;
export type AnswerSource = { title: string; excerpt: string };
export type ReadResult = { label: string; columns: string[]; rows: string[][]; truncated: boolean };
export type AnswerSurface = { kind: "answer"; id: string; text: string; sources: AnswerSource[]; results: ReadResult[] };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function string(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length <= max;
}
function source(value: unknown): value is AnswerSource {
  return object(value) && string(value.title, 300) && value.title.length > 0 && string(value.excerpt, 2000);
}
function result(value: unknown): value is ReadResult {
  return object(value) && string(value.label, 100) && typeof value.truncated === "boolean"
    && Array.isArray(value.columns) && value.columns.length > 0 && value.columns.length <= 8
    && value.columns.every(column => string(column, 100))
    && validRows(value.rows, value.columns.length);
}

function validRows(value: unknown, columns: number): value is string[][] {
  return Array.isArray(value) && value.length <= 20
    && value.every(row => Array.isArray(row) && row.length === columns && row.every(cell => string(cell, 500)));
}

export function parseAnswerSnapshots(value: unknown): Record<string, AnswerSurface> {
  const surfaces: Record<string, AnswerSurface> = Object.create(null);
  if (!object(value)) return surfaces;
  for (const [id, messages] of Object.entries(value).slice(-40)) {
    if (!/^msg_[A-Za-z0-9_-]{1,100}$/.test(id) || !Array.isArray(messages) || messages.length !== 3) continue;
    const [create, components, update] = messages;
    if (!object(create) || create.version !== "v0.9.1" || !object(create.createSurface)
      || create.createSurface.surfaceId !== id || create.createSurface.catalogId !== ANSWER_CATALOG) continue;
    if (!object(components) || components.version !== "v0.9.1" || !object(components.updateComponents) || components.updateComponents.surfaceId !== id) continue;
    const roots = components.updateComponents.components;
    if (!Array.isArray(roots) || roots.length !== 1 || !object(roots[0])) continue;
    const root = roots[0];
    if (Object.keys(root).sort().join() !== "component,data,id" || root.id !== "root" || root.component !== "Answer" || !object(root.data) || root.data.path !== "/answer") continue;
    if (!object(update) || update.version !== "v0.9.1" || !object(update.updateDataModel) || update.updateDataModel.surfaceId !== id || update.updateDataModel.path !== "/answer") continue;
    const data = update.updateDataModel.value;
    if (!object(data) || !string(data.text, 64000) || !Array.isArray(data.sources) || data.sources.length > 8 || !data.sources.every(source)
      || !Array.isArray(data.results) || data.results.length > 5 || !data.results.every(result)) continue;
    surfaces[id] = { kind: "answer", id, text: data.text, sources: data.sources, results: data.results };
  }
  return surfaces;
}
