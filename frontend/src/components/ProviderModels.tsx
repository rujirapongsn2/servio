"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { getApiBaseUrl } from "@/lib/api";

type Provider = { id: number; name: string };
type RegisteredModel = {
  id: number;
  provider_id: number;
  model_id: string;
  display_name: string | null;
  capabilities: string[];
  enabled: boolean;
};
type ImageDefaults = { image_ocr: number | null; image_qa: number | null };
type ModelForm = {
  id: number | null;
  model_id: string;
  display_name: string;
  vision: boolean;
  enabled: boolean;
};
const emptyForm: ModelForm = { id: null, model_id: "", display_name: "", vision: false, enabled: true };
const fieldClass = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900";

function isRegisteredModel(value: unknown): value is RegisteredModel {
  return typeof value === "object" && value !== null && "id" in value && typeof value.id === "number"
    && "provider_id" in value && typeof value.provider_id === "number"
    && "model_id" in value && typeof value.model_id === "string"
    && "display_name" in value && (value.display_name === null || typeof value.display_name === "string")
    && "capabilities" in value && Array.isArray(value.capabilities) && value.capabilities.every((item: unknown) => typeof item === "string")
    && "enabled" in value && typeof value.enabled === "boolean";
}
function parseModels(value: unknown): RegisteredModel[] {
  if (!Array.isArray(value) || !value.every(isRegisteredModel)) throw new Error("Invalid model catalog response");
  return value;
}
function parseDefaults(value: unknown): ImageDefaults {
  if (typeof value === "object" && value !== null && "image_ocr" in value && "image_qa" in value
    && (value.image_ocr === null || typeof value.image_ocr === "number")
    && (value.image_qa === null || typeof value.image_qa === "number")) {
    return { image_ocr: value.image_ocr, image_qa: value.image_qa };
  }
  throw new Error("Invalid image model defaults response");
}
async function apiRequest(path: string, method = "GET", body?: object): Promise<unknown> {
  const response = await fetch(`${getApiBaseUrl()}/api/admin${path}`, {
    method,
    headers: { Authorization: `Bearer ${localStorage.getItem("adminToken")}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data && typeof data.detail === "string" ? data.detail : "Request failed";
    throw new Error(detail);
  }
  return data;
}

export function ProviderModels({ provider, providers, onClose }: { provider: Provider; providers: Provider[]; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [models, setModels] = useState<RegisteredModel[]>([]);
  const [defaults, setDefaults] = useState<ImageDefaults>({ image_ocr: null, image_qa: null });
  const [form, setForm] = useState<ModelForm | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const [catalogs, imageDefaults] = await Promise.all([
      Promise.all(providers.map(async (item) => parseModels(await apiRequest(`/llm-providers/${item.id}/registered-models`)))),
      apiRequest("/image-model-defaults"),
    ]);
    setModels(catalogs.flat());
    setDefaults(parseDefaults(imageDefaults));
    setReady(true);
  }, [providers]);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  useEffect(() => {
    load().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Failed to load models"))
      .finally(() => setLoading(false));
  }, [load]);

  const mutate = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await operation();
      await load();
      setForm(null);
      setDeleting(null);
      setNotice(success);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Failed to save changes");
    } finally {
      setBusy(false);
    }
  };
  const saveModel = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) return;
    const current = form;
    void mutate(() => apiRequest(`/llm-providers/${provider.id}/registered-models${current.id === null ? "" : `/${current.id}`}`,
      current.id === null ? "POST" : "PUT", {
        model_id: current.model_id.trim(), display_name: current.display_name.trim() || null,
        capabilities: current.vision ? ["text", "vision"] : ["text"], enabled: current.enabled,
      }), "Model saved");
  };
  const visionModels = models.filter((model) => model.enabled && model.capabilities.includes("vision"));

  return (
    <dialog ref={dialogRef} aria-labelledby="provider-models-title" onCancel={onClose}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-3xl overflow-y-auto rounded-xl bg-white p-4 text-gray-900 shadow-xl backdrop:bg-black/50 sm:p-6 dark:bg-gray-800 dark:text-white">
      <div className="mb-5 flex items-center justify-between gap-3">
        <h2 id="provider-models-title" className="min-w-0 break-words text-xl font-semibold">Models · {provider.name}</h2>
        <button type="button" onClick={onClose} aria-label="Close model settings" className="shrink-0 rounded p-2 hover:bg-gray-100 dark:hover:bg-gray-700"><X className="h-5 w-5" /></button>
      </div>
      {error && <p role="alert" className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {notice && <p role="status" className="mb-4 text-sm text-green-700 dark:text-green-400">{notice}</p>}
      {loading ? <div role="status" aria-label="Loading models" className="flex justify-center p-6"><Loader2 className="h-6 w-6 animate-spin" /></div> : !ready ? <Button type="button" variant="outline" onClick={() => { setLoading(true); setError(""); void load().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Failed to load models")).finally(() => setLoading(false)); }}>Retry</Button> : (
        <div className="space-y-6">
          <section aria-label="Registered models">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="font-semibold">Registered models</h3>
              <Button type="button" variant="outline" disabled={busy} onClick={() => { setForm({ ...emptyForm }); setDeleting(null); setError(""); }}><Plus className="mr-1 h-4 w-4" />Add Model</Button>
            </div>
            <ul className="divide-y divide-gray-200 dark:divide-gray-700">
              {models.filter((model) => model.provider_id === provider.id).map((model) => (
                <li key={model.id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0 flex-1 break-words">
                      <div className="font-medium">{model.display_name || model.model_id}</div>
                      {model.display_name && <div className="break-all font-mono text-xs text-gray-500 dark:text-gray-400">{model.model_id}</div>}
                      <div className="mt-1 flex flex-wrap gap-1 text-xs"><span className="rounded bg-gray-100 px-2 py-0.5 dark:bg-gray-700">{model.capabilities.includes("vision") ? "Vision" : "Text"}</span>{!model.enabled && <span className="rounded bg-gray-100 px-2 py-0.5 dark:bg-gray-700">Disabled</span>}</div>
                    </div>
                    <div className="flex gap-3 text-sm">
                      <button type="button" disabled={busy} aria-label={`Edit model ${model.model_id}`} className="text-blue-600 dark:text-blue-400" onClick={() => { setForm({ id: model.id, model_id: model.model_id, display_name: model.display_name || "", vision: model.capabilities.includes("vision"), enabled: model.enabled }); setDeleting(null); }}>Edit</button>
                      <button type="button" disabled={busy} aria-label={`Delete model ${model.model_id}`} className="text-red-600 dark:text-red-400" onClick={() => { setDeleting(model.id); setForm(null); }}>Delete</button>
                    </div>
                  </div>
                  {deleting === model.id && <div className="mt-3 flex flex-wrap items-center gap-3 rounded border border-red-200 p-3 text-sm"><span>Delete {model.model_id}?</span><button type="button" disabled={busy} className="font-medium text-red-600" onClick={() => void mutate(() => apiRequest(`/llm-providers/${provider.id}/registered-models/${model.id}`, "DELETE"), "Model deleted")}>Confirm delete</button><button type="button" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button></div>}
                </li>
              ))}
            </ul>
            {!models.some((model) => model.provider_id === provider.id) && !form && <p className="py-4 text-sm text-gray-500">No registered models</p>}
            {form && <form onSubmit={saveModel} className="mt-3 space-y-3 rounded-lg border border-gray-200 p-4 dark:border-gray-600">
              <h4 className="font-medium">{form.id === null ? "Add Model" : "Edit Model"}</h4>
              <div><label htmlFor="catalog-model-id" className="mb-1 block text-sm font-medium">Model ID</label><input id="catalog-model-id" required value={form.model_id} onChange={(event) => setForm({ ...form, model_id: event.target.value })} className={`${fieldClass} font-mono`} autoFocus disabled={busy} /></div>
              <div><label htmlFor="catalog-model-name" className="mb-1 block text-sm font-medium">Display name <span className="font-normal text-gray-500">(optional)</span></label><input id="catalog-model-name" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} className={fieldClass} disabled={busy} /></div>
              <div className="flex flex-wrap gap-5"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.vision} onChange={(event) => setForm({ ...form, vision: event.target.checked })} disabled={busy} />Vision model</label><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} disabled={busy} />Enabled</label></div>
              <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={busy} onClick={() => setForm(null)}>Cancel</Button><Button type="submit" disabled={busy || !form.model_id.trim()}>{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save Model</Button></div>
            </form>}
          </section>
          <section aria-labelledby="image-defaults-title" className="border-t border-gray-200 pt-5 dark:border-gray-600">
            <h3 id="image-defaults-title" className="mb-3 font-semibold">Image task defaults</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {(["image_ocr", "image_qa"] satisfies (keyof ImageDefaults)[]).map((purpose) => (
                <div key={purpose}><label htmlFor={`default-${purpose}`} className="mb-1 block text-sm font-medium">{purpose === "image_ocr" ? "JPG/PNG OCR" : "Image Q&A"}</label>
                  <select id={`default-${purpose}`} value={defaults[purpose] ?? ""} disabled={busy} onChange={(event) => setDefaults({ ...defaults, [purpose]: event.target.value ? Number(event.target.value) : null })} className={fieldClass}>
                    <option value="">Not configured</option>
                    {visionModels.map((model) => <option key={model.id} value={model.id}>{providers.find((item) => item.id === model.provider_id)?.name} · {model.display_name || model.model_id}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end"><Button type="button" disabled={busy} onClick={() => void mutate(() => apiRequest("/image-model-defaults", "PUT", defaults), "Image defaults saved")}>Save Defaults</Button></div>
          </section>
        </div>
      )}
    </dialog>
  );
}
