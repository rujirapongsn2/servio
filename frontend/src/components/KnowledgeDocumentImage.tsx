"use client";

import { useEffect, useRef, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";

type KnowledgeDocumentImageProps = {
  bundleId: number;
  conceptId: string;
  title: string;
  teamAgentId?: number | null;
  thumbnail?: boolean;
};

type ImageState =
  | { kind: "loading" }
  | { kind: "ready"; url: string }
  | { kind: "error" };

export function KnowledgeDocumentImage(props: KnowledgeDocumentImageProps) {
  return <DocumentImage key={JSON.stringify([props.bundleId, props.conceptId, props.teamAgentId ?? null, !!props.thumbnail])} {...props} />;
}

function DocumentImage({ bundleId, conceptId, title, teamAgentId, thumbnail = false }: KnowledgeDocumentImageProps) {
  const [state, setState] = useState<ImageState>({ kind: "loading" });
  const [visible, setVisible] = useState(!thumbnail);
  const [attempt, setAttempt] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const container = useRef<HTMLSpanElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!thumbnail) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    });
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [thumbnail]);

  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setState({ kind: "loading" });
    async function load() {
      try {
        const token = localStorage.getItem("adminToken");
        if (!token) throw new Error("Missing admin token");
        const params = new URLSearchParams({ concept_id: conceptId });
        if (teamAgentId != null) params.set("team_agent_id", String(teamAgentId));
        if (thumbnail) params.set("thumbnail", "true");
        const response = await fetch(`${getApiBaseUrl()}/api/admin/okf-bundles/${bundleId}/image?${params}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("Image unavailable");
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (blob.type !== "image/jpeg" && blob.type !== "image/png") throw new Error("Unsupported image");
        objectUrl = URL.createObjectURL(blob);
        setState({ kind: "ready", url: objectUrl });
      } catch {
        if (!controller.signal.aborted) setState({ kind: "error" });
      }
    }
    void load();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attempt, bundleId, conceptId, teamAgentId, thumbnail, visible]);

  useEffect(() => {
    if (expanded) dialog.current?.showModal();
  }, [expanded]);

  function close() {
    dialog.current?.close();
    setExpanded(false);
    trigger.current?.focus();
  }

  function retry() {
    setState({ kind: "loading" });
    setAttempt((value) => value + 1);
  }

  if (thumbnail) {
    return <span ref={container} aria-hidden="true" className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded border border-gray-200 bg-gray-50 text-xs text-gray-400 dark:border-gray-700 dark:bg-gray-900">
      {state.kind === "ready" ? <img src={state.url} alt="" loading="lazy" className="h-14 w-14 object-contain" onError={() => setState({ kind: "error" })} /> : <span>{state.kind === "error" ? "×" : "…"}</span>}
    </span>;
  }

  function imageContent(inDialog: boolean) {
    if (state.kind === "loading") return <div role="status" className="flex min-h-32 items-center justify-center text-sm text-gray-500">Loading image…</div>;
    if (state.kind === "error") return <div role="status" className="flex min-h-32 items-center justify-center gap-3 text-sm text-gray-500"><span>Image unavailable</span><button type="button" onClick={retry} className="rounded border border-gray-300 px-3 py-1.5 text-gray-900 dark:border-gray-600 dark:text-gray-100">Retry</button></div>;
    return <img src={state.url} alt={title || "Original document image"} className={`${inDialog ? "max-h-[80dvh]" : "max-h-[50dvh]"} w-full object-contain`} onError={() => setState({ kind: "error" })} />;
  }

  return <section aria-label="Original image" className="min-w-0 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
    <div className="flex items-center justify-between gap-3 px-3 py-2">
      <h3 className="text-sm font-medium">Original image</h3>
      <button type="button" disabled={state.kind !== "ready"} onClick={(event) => { trigger.current = event.currentTarget; setExpanded(true); }} aria-label={`Expand original image${title ? ` ${title}` : ""}`} className="rounded px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-40 dark:text-blue-400 dark:hover:bg-gray-800">Expand</button>
    </div>
    <div className="bg-gray-50 p-2 dark:bg-gray-950">{imageContent(false)}</div>
    <dialog ref={dialog} aria-label={title || "Original image"} onCancel={(event) => { event.preventDefault(); event.stopPropagation(); close(); }} onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }} onClick={(event) => event.stopPropagation()} onClose={() => { setExpanded(false); trigger.current?.focus(); }} className="m-auto max-h-[95dvh] w-[calc(100%_-_2rem)] max-w-6xl overflow-auto rounded-xl bg-white p-4 text-gray-900 shadow-xl backdrop:bg-black/60 dark:bg-gray-900 dark:text-gray-100">
      {expanded && <><div className="mb-3 flex items-center justify-between gap-3"><div className="min-w-0 truncate font-medium">{title || "Original image"}</div><button type="button" autoFocus onClick={close} aria-label="Close original image" className="shrink-0 rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600">Close</button></div>{imageContent(true)}</>}
    </dialog>
  </section>;
}
