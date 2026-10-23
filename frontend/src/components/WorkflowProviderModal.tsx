"use client";

import { useEffect, useRef, useState } from "react";
import { workflowRequest } from "@/lib/team-workflow";
export default function WorkflowProviderModal({ onClose, onCreated }: { onClose: () => void; onCreated: (providerId: number) => Promise<void> }) {
  const [name, setName] = useState(""); const [baseUrl, setBaseUrl] = useState(""); const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const active = useRef(false); const createdId = useRef<number | null>(null);
  const modal = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    modal.current?.querySelector<HTMLInputElement>("input")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !active.current) { event.preventDefault(); onClose(); }
      if (event.key === "Tab") {
        const controls = Array.from(modal.current?.querySelectorAll<HTMLElement>("input:not(:disabled), button:not(:disabled)") ?? []);
        const first = controls[0]; const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); if (previous instanceof HTMLElement) previous.focus(); };
  }, [onClose]);
  const submit = async () => {
    if (active.current) return; active.current = true; setBusy(true); setError("");
    try {
      if (createdId.current === null) {
        const result = await workflowRequest("/llm-providers", { method: "POST", body: JSON.stringify({ name: name.trim(), base_url: baseUrl.trim(), api_key: apiKey, is_default: false }) });
        if (!result || typeof result !== "object" || !("provider_id" in result) || typeof result.provider_id !== "number" || !Number.isSafeInteger(result.provider_id) || result.provider_id < 1) throw Error("Provider created. Close and reopen Workflow to refresh providers.");
        createdId.current = result.provider_id;
      }
      await onCreated(createdId.current);
    } catch (failure: unknown) { setError(failure instanceof Error ? failure.message : "Unable to create provider."); }
    finally { active.current = false; setBusy(false); }
  };
  return <div role="dialog" aria-modal="true" aria-labelledby="workflow-provider-title" className="fixed inset-0 z-[100] grid place-items-center bg-slate-950/40 p-4"><form ref={modal} onSubmit={(event) => { event.preventDefault(); void submit(); }} className="max-h-[90dvh] w-full max-w-lg space-y-4 overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
    <h2 id="workflow-provider-title" className="font-semibold">Create provider</h2>{error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    <fieldset disabled={busy || createdId.current !== null} className="space-y-3">{[{ label: "Provider name", value: name, change: setName, type: "text" }, { label: "Base URL", value: baseUrl, change: setBaseUrl, type: "url" }, { label: "API key", value: apiKey, change: setApiKey, type: "password" }].map((field) => <label key={field.label} className="block text-sm">{field.label}<input required type={field.type} value={field.value} onChange={(event) => field.change(event.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2" /></label>)}</fieldset>
    <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose} className="px-3 py-2 text-sm">Cancel</button><button type="submit" disabled={busy} className="rounded-lg bg-sky-600 px-3 py-2 text-sm text-white">{busy ? "Creating…" : createdId.current ? "Refresh providers" : "Create provider"}</button></div>
  </form></div>;
}
