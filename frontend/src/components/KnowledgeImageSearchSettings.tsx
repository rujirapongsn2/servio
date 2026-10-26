"use client";

import { useEffect, useId, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";

type Settings = {
  mode: "similarity" | "rerank";
  default_min_score: number;
  override_min_score: number | null;
  effective_min_score: number;
  can_edit: boolean;
};
type SaveState = { kind: "idle" | "saving" | "saved" } | { kind: "error"; message: string; stale: boolean };
type State = { kind: "loading" } | { kind: "error" } | {
  kind: "ready";
  settings: Settings;
  draft: string;
  save: SaveState;
};

function score(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= -1 && value <= 1;
}
function parseSettings(value: unknown): Settings {
  if (value === null || typeof value !== "object" || !("mode" in value)
    || (value.mode !== "similarity" && value.mode !== "rerank")
    || !("default_min_score" in value) || !score(value.default_min_score)
    || !("override_min_score" in value) || (value.override_min_score !== null && !score(value.override_min_score))
    || !("effective_min_score" in value) || !score(value.effective_min_score)
    || !("can_edit" in value) || typeof value.can_edit !== "boolean") {
    throw new Error("Invalid image search settings");
  }
  return { mode: value.mode, default_min_score: value.default_min_score, override_min_score: value.override_min_score, effective_min_score: value.effective_min_score, can_edit: value.can_edit };
}
function percent(value: number): string {
  return String(Number((value * 100).toFixed(5)));
}

export function KnowledgeImageSearchSettings({ bundleId, teamAgentId, canEdit }: {
  bundleId: number;
  teamAgentId?: number | null;
  canEdit: boolean;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reload, setReload] = useState(0);
  const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
  const url = `${getApiBaseUrl()}/api/admin/okf-bundles/${bundleId}/image-search-settings${params}`;
  const inputId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    async function load() {
      try {
        const response = await fetch(url, { signal: controller.signal, headers: { Authorization: `Bearer ${localStorage.getItem("adminToken")}` } });
        if (!response.ok) throw new Error("Load failed");
        const settings = parseSettings(await response.json());
        if (!controller.signal.aborted) setState({ kind: "ready", settings, draft: percent(settings.effective_min_score), save: { kind: "idle" } });
      } catch {
        if (!controller.signal.aborted) setState({ kind: "error" });
      }
    }
    void load();
    return () => controller.abort();
  }, [url, reload]);

  async function save(value: number | null) {
    if (state.kind !== "ready" || state.save.kind === "saving" || !canEdit || !state.settings.can_edit) return;
    const current = state;
    setState({ ...current, save: { kind: "saving" } });
    try {
      const response = await fetch(url, { method: "PATCH", headers: { Authorization: `Bearer ${localStorage.getItem("adminToken")}`, "Content-Type": "application/json" }, body: JSON.stringify({ mode: current.settings.mode, min_score: value }) });
      if (!response.ok) {
        setState({ ...current, save: { kind: "error", stale: response.status === 409, message: response.status === 409 ? "โหมดค้นหาเปลี่ยนแล้ว กรุณาโหลดค่าล่าสุด" : "บันทึกไม่สำเร็จ กรุณาลองอีกครั้ง" } });
        return;
      }
      const settings = parseSettings(await response.json());
      setState({ kind: "ready", settings, draft: percent(settings.effective_min_score), save: { kind: "saved" } });
    } catch {
      setState({ ...current, save: { kind: "error", stale: false, message: "บันทึกไม่สำเร็จ กรุณาลองอีกครั้ง" } });
    }
  }

  const editable = state.kind === "ready" && canEdit && state.settings.can_edit;
  const busy = state.kind === "ready" && state.save.kind === "saving";
  const value = state.kind === "ready" && state.draft.trim() !== "" ? Number(state.draft) / 100 : NaN;
  const valid = score(value);
  const dirty = state.kind === "ready" && state.draft !== percent(state.settings.effective_min_score);
  const stale = state.kind === "ready" && state.save.kind === "error" && state.save.stale;

  const aiSelection = state.kind === "ready" && state.settings.mode === "rerank";
  const modeLabel = aiSelection ? "AI ช่วยคัดเลือกภาพ" : "ค้นหาด้วยความคล้าย";
  const defaultVariable = aiSelection ? "MULTIMODAL_IMAGE_RERANK_CANDIDATE_MIN_SCORE" : "MULTIMODAL_IMAGE_QUERY_MIN_SCORE";

  return <section aria-label="ตั้งค่าการค้นหาจากรูปภาพ" aria-busy={busy} className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
    <div className="flex flex-wrap items-center gap-2">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-white">ค้นหาจากรูปภาพ</h3>
      {state.kind === "ready" && <span className="rounded-full bg-sky-50 px-2 py-1 text-xs font-medium text-sky-800 dark:bg-sky-950 dark:text-sky-200">{modeLabel}</span>}
    </div>
    {state.kind === "loading" && <p role="status" className="mt-3 text-sm text-gray-500">กำลังโหลดการตั้งค่า…</p>}
    {state.kind === "error" && <div className="mt-3 flex flex-wrap items-center gap-3"><p role="alert" className="text-sm text-red-600">โหลดการตั้งค่าไม่สำเร็จ</p><button type="button" onClick={() => setReload((value) => value + 1)} className="text-sm text-sky-700 underline dark:text-sky-300">ลองอีกครั้ง</button></div>}
    {state.kind === "ready" && <>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-900 dark:text-white">ระดับความคล้ายของรูปภาพ</label>
          <div className="mt-2 flex items-center gap-2">
            <input id={inputId} type="number" min="-100" max="100" step="any" required value={state.draft} readOnly={!editable} disabled={busy || stale} aria-invalid={!valid} aria-describedby={`${inputId}-help`} onChange={(event) => setState({ ...state, draft: event.target.value, save: { kind: "idle" } })} className="w-28 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-sky-500 focus:ring-2 focus:ring-sky-200 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-800 dark:text-white" />
            <span className="text-sm text-gray-600 dark:text-gray-300">%</span>
          </div>
        </div>
        <p className="pb-2 text-xs text-gray-600 dark:text-gray-300">{state.settings.override_min_score === null ? `ใช้ค่าเริ่มต้นของโหมดนี้ ${percent(state.settings.default_min_score)}%` : `กำหนดเอง · ค่าเริ่มต้นของโหมดนี้ ${percent(state.settings.default_min_score)}%`}</p>
      </div>
      <p id={`${inputId}-help`} className="mt-3 text-xs leading-5 text-gray-600 dark:text-gray-300">เพิ่มค่าเพื่อเลือกภาพที่คล้ายมากขึ้น ลดค่าเพื่อค้นหาได้กว้างขึ้น</p>
      {editable && !valid && <p role="alert" className="mt-2 text-xs text-red-600">ระบุระดับตั้งแต่ -100 ถึง 100%</p>}
      {editable && <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" aria-label="บันทึกระดับความคล้าย" disabled={busy || stale || !valid || !dirty} onClick={() => void save(value)} className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:opacity-50">{busy ? "กำลังบันทึก…" : "บันทึก"}</button>
        <button type="button" aria-label="กลับไปใช้ค่าเริ่มต้นของโหมดนี้" disabled={busy || stale || state.settings.override_min_score === null} onClick={() => void save(null)} className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800">กลับไปใช้ค่าเริ่มต้น</button>
      </div>}
      <div aria-live="polite" className="mt-2 text-sm">
        {state.save.kind === "saved" && <p className="text-emerald-700 dark:text-emerald-300">บันทึกแล้ว</p>}
        {state.save.kind === "error" && <p role="alert" className="text-red-600 dark:text-red-300">{state.save.message}</p>}
      </div>
      <details className="mt-3 text-xs text-gray-600 dark:text-gray-300">
        <summary className="cursor-pointer select-none">รายละเอียดการตั้งค่า</summary>
        <div className="mt-2 space-y-2 leading-5">
          <p>{aiSelection ? "ระดับนี้ใช้คัดภาพเบื้องต้น ก่อนให้ AI ตรวจประเภทสินค้าและเรียงลำดับภาพ" : "ระดับนี้ใช้คัดภาพตามคะแนนความคล้าย"} เปอร์เซ็นต์นี้ไม่ใช่ความแม่นยำของ AI</p>
          <p>ตัวแปรค่าเริ่มต้นใน .env: <code className="break-all">{defaultVariable}</code></p>
          <p>{aiSelection ? "หากไม่ได้กำหนดตัวแปรนี้ ระบบใช้ 20% ส่วน MULTIMODAL_IMAGE_QUERY_MIN_SCORE ใช้ในโหมดค้นหาด้วยความคล้าย" : "หากไม่ได้กำหนดตัวแปรนี้ ระบบใช้ 82%"}</p>
        </div>
      </details>
      {stale && <button type="button" onClick={() => setReload((value) => value + 1)} className="mt-2 text-sm text-sky-700 underline dark:text-sky-300">โหลดค่าล่าสุด</button>}
    </>}
  </section>;
}
