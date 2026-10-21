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
export type ProductPresentations = Record<string, ProductCarouselPresentation>;

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
    const carousel = parseProductCarousel(raw);
    if (carousel) result[callId] = carousel;
  }
  return result;
}
