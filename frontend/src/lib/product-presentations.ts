export interface Product {
  id: string;
  title: string;
  image_url?: string;
  part_number?: string;
  brand?: string;
  price_text?: string;
  description?: string;
  detail_url?: string;
}
export interface ProductCarouselPresentation {
  type: "product_carousel";
  version: 1;
  summary: string;
  products: Product[];
}
export interface KnowledgeImage {
  asset_id: string;
  title: string;
  source_label: string;
  image_url: string;
}
export interface KnowledgeImagesPresentation {
  type: "knowledge_images";
  version: 1;
  response: string;
  images: KnowledgeImage[];
}
export type ProductPresentations = Record<string, ProductCarouselPresentation | KnowledgeImagesPresentation | KnowledgeMediaPresentation | KnowledgeProductCarouselPresentation>;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}
function safeUrl(value: string): boolean {
  if (/[\x00-\x20\x7f\\]/.test(value)) return false;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    if (url.protocol !== "https:" || url.username || url.password || !host.includes(".")) return false;
    if (host === "localhost" || /\.(localhost|local|internal)$/.test(host) || host.includes(":")) return false;
    if (/^[0-9.]+$/.test(host)) {
      const [a, b, c] = host.split(".").map(Number);
      if (a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || (a === 192 && b === 0 && (c === 0 || c === 2)) || (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) || (a === 203 && b === 0 && c === 113)) return false;
    }
    return true;
  } catch { return false; }
}
export function parseProductCarousel(value: unknown): ProductCarouselPresentation | null {
  if (!isObject(value) || value.type !== "product_carousel" || value.version !== 1 || !text(value.summary, 1000)) return null;
  if (Object.keys(value).some((key) => !["type", "version", "summary", "products"].includes(key))) return null;
  if (!Array.isArray(value.products) || value.products.length < 1 || value.products.length > 10 || JSON.stringify(value).length > 64000) return null;
  const products: Product[] = [];
  const ids = new Set<string>();
  for (const raw of value.products) {
    if (!isObject(raw) || !text(raw.id, 128) || !text(raw.title, 200) || ids.has(raw.id)) return null;
    const product: Product = { id: raw.id, title: raw.title };
    const limits = { image_url: 2048, part_number: 128, brand: 128, price_text: 100, description: 4000, detail_url: 2048 };
    if (Object.keys(raw).some((key) => !["id", "title", ...Object.keys(limits)].includes(key))) return null;
    for (const key of Object.keys(limits) as (keyof typeof limits)[]) {
      const field = raw[key];
      if (field === undefined || field === null) continue;
      if (typeof field !== "string" || field.length > limits[key]) return null;
      if ((key === "image_url" || key === "detail_url") && !safeUrl(field)) return null;
      product[key] = field;
    }
    ids.add(raw.id);
    products.push(product);
  }
  return { type: "product_carousel", version: 1, summary: value.summary, products };
}
export function parseProductPresentations(value: unknown): ProductPresentations {
  const result: ProductPresentations = Object.create(null);
  if (!isObject(value)) return result;
  for (const [callId, raw] of Object.entries(value).slice(0, 50)) {
    const carousel = parseProductCarousel(raw) || parseKnowledgeProductCarousel(raw) || parseKnowledgeImages(raw) || parseKnowledgeMedia(raw);
    if (carousel) result[callId] = carousel;
  }
  return result;
}

export function parseKnowledgeImages(value: unknown): KnowledgeImagesPresentation | null {
  if (!isObject(value) || value.type !== "knowledge_images" || value.version !== 1 || typeof value.response !== "string" || value.response.length > 64000) return null;
  if (Object.keys(value).some((key) => !["type", "version", "response", "images"].includes(key))) return null;
  if (!Array.isArray(value.images) || value.images.length < 1 || value.images.length > 5) return null;
  const images: KnowledgeImage[] = [];
  for (const raw of value.images) {
    if (!isObject(raw) || !text(raw.asset_id, 64) || !/^[a-f0-9]{64}$/.test(raw.asset_id) || !text(raw.title, 1000) || !text(raw.source_label, 2000) || !text(raw.image_url, 4096)) return null;
    if (Object.keys(raw).some((key) => !["asset_id", "title", "source_label", "image_url"].includes(key))) return null;
    if (!new RegExp(`^/api/knowledge-images/${raw.asset_id}\\?token=[A-Za-z0-9_.-]+$`).test(raw.image_url)) return null;
    images.push({ asset_id: raw.asset_id, title: raw.title, source_label: raw.source_label, image_url: raw.image_url });
  }
  return { type: "knowledge_images", version: 1, response: value.response, images };
}

export interface KnowledgeAudioClip {
  asset_id: string;
  title: string;
  source_label: string;
  segment_id: string;
  start_ms: number;
  end_ms: number;
  transcript: string;
  transcript_status: "ready" | "empty";
  audio_url: string;
}
export interface KnowledgeMediaPresentation {
  type: "knowledge_media";
  version: 1;
  response: string;
  images: KnowledgeImage[];
  audio: KnowledgeAudioClip[];
}
export function parseKnowledgeAudio(value: unknown): KnowledgeAudioClip[] {
  if (!Array.isArray(value) || value.length > 5) return [];
  const result: KnowledgeAudioClip[] = [];
  for (const raw of value) {
    if (!isObject(raw) || !text(raw.asset_id, 64) || !/^[a-f0-9]{64}$/.test(raw.asset_id) || !text(raw.title, 1000) || !text(raw.source_label, 2000) || !text(raw.segment_id, 5) || !/^s[0-9]{4}$/.test(raw.segment_id)) return [];
    if (typeof raw.start_ms !== "number" || !Number.isInteger(raw.start_ms) || raw.start_ms < 0 || typeof raw.end_ms !== "number" || !Number.isInteger(raw.end_ms) || raw.end_ms <= raw.start_ms || raw.end_ms > 600000 || raw.end_ms - raw.start_ms > 60000) return [];
    if (typeof raw.transcript !== "string" || raw.transcript.length > 20000 || (raw.transcript_status !== "ready" && raw.transcript_status !== "empty") || !text(raw.audio_url, 4096)) return [];
    if (!new RegExp(`^/api/knowledge-audio/${raw.asset_id}\\?token=[A-Za-z0-9_.-]+$`).test(raw.audio_url)) return [];
    if (Object.keys(raw).some((key) => !["asset_id", "title", "source_label", "segment_id", "start_ms", "end_ms", "transcript", "transcript_status", "audio_url"].includes(key))) return [];
    result.push({ asset_id: raw.asset_id, title: raw.title, source_label: raw.source_label, segment_id: raw.segment_id, start_ms: raw.start_ms, end_ms: raw.end_ms, transcript: raw.transcript, transcript_status: raw.transcript_status, audio_url: raw.audio_url });
  }
  return result;
}
export function parseKnowledgeMedia(value: unknown): KnowledgeMediaPresentation | null {
  if (!isObject(value) || value.type !== "knowledge_media" || value.version !== 1 || typeof value.response !== "string" || value.response.length > 64000) return null;
  if (Object.keys(value).some((key) => !["type", "version", "response", "images", "audio"].includes(key))) return null;
  const audio = parseKnowledgeAudio(value.audio);
  if (!audio.length) return null;
  const images = Array.isArray(value.images) && value.images.length ? parseKnowledgeImages({ type: "knowledge_images", version: 1, response: value.response, images: value.images })?.images : [];
  if (!images) return null;
  return { type: "knowledge_media", version: 1, response: value.response, audio, images };
}

export interface KnowledgeProduct extends Product {
  asset_id: string;
  source_label: string;
  image_url: string;
  description: string;
}
export interface KnowledgeProductCarouselPresentation {
  type: "knowledge_product_carousel";
  version: 1;
  summary: string;
  products: KnowledgeProduct[];
}
export function parseKnowledgeProductCarousel(value: unknown): KnowledgeProductCarouselPresentation | null {
  if (!isObject(value) || value.type !== "knowledge_product_carousel" || value.version !== 1 || !text(value.summary, 1000)) return null;
  if (Object.keys(value).some((key) => !["type", "version", "summary", "products"].includes(key))) return null;
  if (!Array.isArray(value.products) || value.products.length < 1 || value.products.length > 5 || JSON.stringify(value).length > 96000) return null;
  const products: KnowledgeProduct[] = [];
  const ids = new Set<string>();
  const assets = new Set<string>();
  for (const raw of value.products) {
    if (!isObject(raw) || !text(raw.id, 32) || !/^[a-f0-9]{32}$/.test(raw.id) || ids.has(raw.id)) return null;
    const parsed = parseKnowledgeImages({ type: "knowledge_images", version: 1, response: "", images: [{ asset_id: raw.asset_id, title: raw.title, source_label: raw.source_label, image_url: raw.image_url }] });
    if (!parsed || typeof raw.description !== "string" || raw.description.length > 8000) return null;
    if (Object.keys(raw).some((key) => !["id", "asset_id", "title", "source_label", "description", "image_url"].includes(key))) return null;
    const image = parsed.images[0];
    if (assets.has(image.asset_id)) return null;
    products.push({ ...image, id: raw.id, description: raw.description });
    ids.add(raw.id);
    assets.add(image.asset_id);
  }
  return { type: "knowledge_product_carousel", version: 1, summary: value.summary, products };
}
