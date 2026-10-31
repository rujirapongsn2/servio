import { ANSWER_CATALOG, parseAnswerSnapshots, type AnswerSurface } from "./a2ui-answers";
import catalog from "./a2ui-discovery.catalog.json";
import { parseKnowledgeProductCarousel, type KnowledgeProduct } from "./product-presentations";

export const DISCOVERY_CATALOG = catalog.catalogId;
export const SUPPORTED_CATALOGS = [DISCOVERY_CATALOG, ANSWER_CATALOG];
export const A2UI_VERSION = "v0.9.1";
export const COLOR_OPTIONS = [
  { value: "similar", label: "สีใกล้เคียง" }, { value: "lighter", label: "สีอ่อนกว่า" },
  { value: "darker", label: "สีเข้มกว่า" }, { value: "any", label: "ทุกโทนสี" },
] as const;
export const PATTERN_OPTIONS = [
  { value: "similar", label: "ลายใกล้เคียง" }, { value: "wood_grain", label: "ลายไม้" },
  { value: "stone_veined", label: "ลายหินเส้น" }, { value: "solid", label: "สีพื้น" },
  { value: "any", label: "ทุกลาย" },
] as const;
export type DiscoveryFilters = {
  color: typeof COLOR_OPTIONS[number]["value"];
  pattern: typeof PATTERN_OPTIONS[number]["value"];
};
export type DiscoverySurface = {
  kind: "discovery"; id: string; active: boolean; summary: string; queryImage: string;
  facets: Record<string, { color: string; pattern: string; category: string }>;
  products: KnowledgeProduct[]; filters: DiscoveryFilters;
};
export type DiscoverySurfaces = Record<string, DiscoverySurface>;
export type A2uiSurfaces = Record<string, DiscoverySurface | AnswerSurface>;
export type DiscoveryAction =
  | { name: "discovery.refine"; context: DiscoveryFilters }
  | { name: "discovery.inquire"; context: { card_id: string } };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function colorValue(value: string): DiscoveryFilters["color"] | null {
  return COLOR_OPTIONS.find(option => option.value === value)?.value ?? null;
}
export function patternValue(value: string): DiscoveryFilters["pattern"] | null {
  return PATTERN_OPTIONS.find(option => option.value === value)?.value ?? null;
}

/** The transport carries bounded, complete A2UI snapshots for history replay. */
export function parseDiscoverySnapshots(value: unknown): DiscoverySurfaces {
  const surfaces: DiscoverySurfaces = Object.create(null);
  if (!object(value)) return surfaces;
  for (const [id, messages] of Object.entries(value).slice(-40)) {
    if (!/^msg_[a-f0-9]{32}$/.test(id) || !Array.isArray(messages) || messages.length !== 3) continue;
    const [create, components, update] = messages;
    if (![create, components, update].every(message => object(message) && message.version === A2UI_VERSION)) continue;
    if (!object(create) || !object(create.createSurface) || create.createSurface.surfaceId !== id || create.createSurface.catalogId !== DISCOVERY_CATALOG) continue;
    if (!object(components) || !object(components.updateComponents) || components.updateComponents.surfaceId !== id) continue;
    const roots = components.updateComponents.components;
    if (!Array.isArray(roots) || roots.length !== 1 || !object(roots[0])) continue;
    const root = roots[0];
    if (root.id !== "root" || root.component !== "ProductDiscovery" || !object(root.data) || root.data.path !== "/discovery") continue;
    if (!object(root.refineAction) || !object(root.refineAction.event) || root.refineAction.event.name !== "discovery.refine" || !object(root.inquireAction) || !object(root.inquireAction.event) || root.inquireAction.event.name !== "discovery.inquire") continue;
    if (!object(update) || !object(update.updateDataModel) || update.updateDataModel.surfaceId !== id || update.updateDataModel.path !== "/discovery") continue;
    const data = update.updateDataModel.value;
    if (!object(data) || typeof data.active !== "boolean" || typeof data.summary !== "string" || data.summary.length > 1000 || !object(data.filters)) continue;
    const color = typeof data.filters.color === "string" ? colorValue(data.filters.color) : null;
    const pattern = typeof data.filters.pattern === "string" ? patternValue(data.filters.pattern) : null;
    if (!color || !pattern || typeof data.queryImage !== "string" || data.queryImage.length > 60000 || !/^data:image\/jpeg;base64,[A-Za-z0-9+/]+=*$/.test(data.queryImage)) continue;
    if (!Array.isArray(data.products) || data.products.length > 5) continue;
    const parsed = data.products.length ? parseKnowledgeProductCarousel({ type: "knowledge_product_carousel", version: 1, summary: data.summary, products: data.products }) : null;
    if (data.products.length && !parsed) continue;
    const facets: DiscoverySurface["facets"] = Object.create(null);
    if (object(data.facets)) {
      for (const [cardId, facet] of Object.entries(data.facets).slice(0, 5)) {
        if (!object(facet) || typeof facet.color !== "string" || facet.color.length > 300 || typeof facet.pattern !== "string" || facet.pattern.length > 300 || typeof facet.category !== "string" || facet.category.length > 100) continue;
        if (parsed?.products.some(product => product.id === cardId)) facets[cardId] = { color: facet.color, pattern: facet.pattern, category: facet.category };
      }
    }
    surfaces[id] = { kind: "discovery", id, facets, active: data.active, summary: data.summary, queryImage: data.queryImage, filters: { color, pattern }, products: parsed?.products ?? [] };
  }
  return surfaces;
}

export function parseA2uiSnapshots(value: unknown): A2uiSurfaces {
  return Object.assign(Object.create(null), parseAnswerSnapshots(value), parseDiscoverySnapshots(value));
}

export function discoveryActionEnvelope(surfaceId: string, action: DiscoveryAction) {
  return { type: "a2ui.action", version: A2UI_VERSION, request_id: crypto.randomUUID(),
    action: { surfaceId, sourceComponentId: "root", timestamp: new Date().toISOString(), ...action } };
}
