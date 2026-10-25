"use client";

import { useEffect, useRef, useState } from "react";

const statuses = {
  healthy: { label: "Healthy", color: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300" },
  unavailable: { label: "Unavailable", color: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" },
  configured: { label: "Configured", color: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300" },
  not_configured: { label: "Not configured", color: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
  disabled: { label: "Disabled", color: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300" },
  unknown: { label: "Unknown", color: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
};

type ServiceStatus = keyof typeof statuses;
interface Service {
  id: string;
  label: string;
  status: ServiceStatus;
  endpoint?: string | null;
  model?: string | null;
  detail: string;
}
interface SystemInfo {
  services: Service[];
  checked_at: string;
  backend_url: string;
  frontend_origin: string | null;
  server_time: string;
  python_version: string;
  mcp_enabled: boolean;
  openai_api_key_set: boolean;
  agents_count: number | null;
  tools_count: number | null;
}

function isStatus(value: unknown): value is ServiceStatus {
  return typeof value === "string" && Object.hasOwn(statuses, value);
}
function isService(value: unknown): value is Service {
  return typeof value === "object" && value !== null
    && "id" in value && typeof value.id === "string"
    && "label" in value && typeof value.label === "string"
    && "status" in value && isStatus(value.status)
    && "detail" in value && typeof value.detail === "string"
    && (!("endpoint" in value) || value.endpoint === null || typeof value.endpoint === "string")
    && (!("model" in value) || value.model === null || typeof value.model === "string");
}
function isSystemInfo(value: unknown): value is SystemInfo {
  return typeof value === "object" && value !== null
    && "services" in value && Array.isArray(value.services) && value.services.every(isService)
    && "checked_at" in value && typeof value.checked_at === "string" && Number.isFinite(Date.parse(value.checked_at))
    && "backend_url" in value && typeof value.backend_url === "string"
    && "frontend_origin" in value && (value.frontend_origin === null || typeof value.frontend_origin === "string")
    && "server_time" in value && typeof value.server_time === "string"
    && "python_version" in value && typeof value.python_version === "string"
    && "mcp_enabled" in value && typeof value.mcp_enabled === "boolean"
    && "openai_api_key_set" in value && typeof value.openai_api_key_set === "boolean"
    && "agents_count" in value && (value.agents_count === null || typeof value.agents_count === "number")
    && "tools_count" in value && (value.tools_count === null || typeof value.tools_count === "number");
}

export function SystemInformation({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const refresh = useRef<() => void>(() => {});

  useEffect(() => {
    let active = true;
    let pending: AbortController | null = null;
    let timer: ReturnType<typeof setInterval> | undefined;
    const fetchInfo = async () => {
      if (!active || document.visibilityState === "hidden" || pending) return;
      const controller = new AbortController();
      pending = controller;
      setLoading(true);
      try {
        const response = await fetch(`${apiBaseUrl}/api/admin/system-info`, {
          headers: { Authorization: `Bearer ${localStorage.getItem("adminToken")}` },
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("System check failed");
        const data: unknown = await response.json();
        if (!isSystemInfo(data)) throw new Error("Invalid system check");
        if (active && pending === controller && !controller.signal.aborted) {
          setInfo(data);
          setFailed(false);
        }
      } catch {
        if (active && pending === controller && !controller.signal.aborted) setFailed(true);
      } finally {
        if (active && pending === controller) {
          pending = null;
          setLoading(false);
        }
      }
    };
    const visibility = () => {
      clearInterval(timer);
      if (document.visibilityState === "hidden") {
        pending?.abort();
        pending = null;
        setLoading(false);
      } else {
        void fetchInfo();
        timer = setInterval(() => void fetchInfo(), 30000);
      }
    };
    refresh.current = () => void fetchInfo();
    document.addEventListener("visibilitychange", visibility);
    visibility();
    return () => {
      active = false;
      pending?.abort();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visibility);
      refresh.current = () => {};
    };
  }, [apiBaseUrl]);

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow dark:border-gray-700 dark:bg-gray-800 sm:p-6" aria-labelledby="system-information-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="system-information-title" className="text-lg font-medium text-gray-900 dark:text-white">System Information</h2>
        <button type="button" onClick={() => refresh.current()} disabled={loading} className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-700" aria-label="Refresh system information">
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>
      <div aria-live="polite" className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        {failed ? <span className="text-amber-700 dark:text-amber-300">{info ? "Update failed · Showing last successful check" : "System information unavailable. Try Refresh."}</span> : info ? <>Checked <time dateTime={info.checked_at}>{new Date(info.checked_at).toLocaleTimeString()}</time></> : "Checking services…"}
      </div>
      {info && <>
        <ul className="divide-y divide-gray-100 dark:divide-gray-700">
          {info.services.map(service => <li key={service.id} className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1 py-3">
            <div className="min-w-0 flex-1 basis-44">
              <div className="text-sm font-medium text-gray-900 dark:text-white">{service.label}</div>
              {(service.endpoint || service.model) && <div className="mt-0.5 break-all font-mono text-xs text-gray-500 dark:text-gray-400">{[service.endpoint, service.model].filter(Boolean).join(" · ")}</div>}
              <div className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{service.detail}</div>
            </div>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statuses[service.status].color}`}>{statuses[service.status].label}</span>
          </li>)}
        </ul>
        <details className="mt-4 border-t border-gray-200 pt-3 text-sm dark:border-gray-700">
          <summary className="cursor-pointer text-gray-700 dark:text-gray-300">Runtime details</summary>
          <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-2 text-xs sm:grid-cols-[auto_minmax(0,1fr)]">
            {[
              ["Backend API", info.backend_url], ["Frontend", info.frontend_origin || "—"],
              ["Server time (UTC)", info.server_time], ["Python", info.python_version],
              ["OpenAI key configured", info.openai_api_key_set ? "Yes" : "No"],
              ["Agents / Tools", `${info.agents_count ?? "—"} / ${info.tools_count ?? "—"}`],
            ].map(([label, value]) => <div key={label} className="contents"><dt className="text-gray-500 dark:text-gray-400">{label}</dt><dd className="break-all text-gray-900 dark:text-gray-100">{value}</dd></div>)}
          </dl>
        </details>
      </>}
    </section>
  );
}
