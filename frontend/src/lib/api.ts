/**
 * Resolve the base URL for backend API calls.
 *
 * Priority:
 * 1. Explicit NEXT_PUBLIC_API_URL env var (without trailing slash)
 * 2. Same origin when running on a non-localhost domain (useful for deployed environments with a reverse proxy)
 * 3. Local development fallback to http://localhost:8000
 */
export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim().length > 0) {
    return envUrl.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    const { origin, hostname } = window.location;
    if (hostname !== "localhost" && hostname !== "127.0.0.1") {
      return origin.replace(/\/$/, "");
    }
  }

  return "http://localhost:8000";
}

export function buildApiUrl(path: string): string {
  const base = getApiBaseUrl();
  if (!path.startsWith("/")) {
    return `${base}/${path}`;
  }
  return `${base}${path}`;
}
