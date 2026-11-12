/** HTML for the public gateway configured by NEXT_PUBLIC_API_URL. */
export function widgetEmbedCode({ baseUrl, apiKey, type = "voice", position, allowToggle, lang, async = false }: {
  baseUrl: string;
  apiKey: string;
  type?: string;
  position?: string;
  allowToggle?: boolean;
  lang?: string;
  async?: boolean;
}): string {
  const url = new URL(baseUrl);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("Widget base URL must be an HTTP(S) public gateway without credentials, query or fragment.");
  }
  const base = url.href.replace(/\/+$/, "");
  const escape = (value: string) => value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const attributes: [string, string][] = [
    ["src", `${base}/embed.js`], ["data-server-url", base], ["data-api-key", apiKey], ["data-type", type],
  ];
  if (position !== undefined) attributes.push(["data-position", position]);
  if (allowToggle !== undefined) attributes.push(["data-allow-toggle", String(allowToggle)]);
  if (lang !== undefined) attributes.push(["data-lang", lang]);
  return `<script ${attributes.map(([name, value]) => `${name}="${escape(value)}"`).join(" ")}${async ? " async" : ""}></script>`;
}
