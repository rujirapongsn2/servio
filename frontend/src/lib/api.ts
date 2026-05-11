function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

function isLocalHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function shouldUseBrowserOrigin(configuredUrl: string, browserOrigin: string): boolean {
  try {
    const configured = new URL(configuredUrl);
    const browser = new URL(browserOrigin);
    return !isLocalHostname(browser.hostname) && isLocalHostname(configured.hostname);
  } catch {
    return false;
  }
}

/**
 * Resolve the base URL for backend API calls.
 *
 * Priority:
 * 1. Explicit NEXT_PUBLIC_API_URL env var, unless it points to localhost while the current page is on a public host
 * 2. Current browser origin
 * 3. Local development fallback to http://localhost:8000
 */
export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

  if (typeof window !== "undefined") {
    const origin = trimTrailingSlash(window.location.origin);
    if (envUrl && !shouldUseBrowserOrigin(envUrl, origin)) {
      return trimTrailingSlash(envUrl);
    }
    return origin;
  }

  if (envUrl) {
    return trimTrailingSlash(envUrl);
  }

  return "http://localhost:8000";
}

export function getWebsocketBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_WEBSOCKET_ENDPOINT?.trim();

  if (typeof window !== "undefined") {
    const browserWsOrigin = trimTrailingSlash(window.location.origin).replace(/^http/, "ws");
    if (envUrl && !shouldUseBrowserOrigin(envUrl, window.location.origin)) {
      return trimTrailingSlash(envUrl);
    }
    return `${browserWsOrigin}/ws`;
  }

  if (envUrl) {
    return trimTrailingSlash(envUrl);
  }

  return "ws://localhost:8000/ws";
}

export function buildApiUrl(path: string): string {
  const base = getApiBaseUrl();
  if (!path.startsWith("/")) {
    return `${base}/${path}`;
  }
  return `${base}${path}`;
}
