"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import CreateToolForm from "@/components/CreateToolForm";
import type { CreatedTool } from "@/lib/tool-creation";

export default function WorkflowToolModal({ teamId, onClose, onCreated }: { teamId: number; onClose: () => void; onCreated: (result: CreatedTool) => void }) {
  const headingId = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const busy = useRef(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => { setHost(document.body); }, []);
  useEffect(() => {
    if (!host) return;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') ?? []).filter(element => !element.closest("fieldset:disabled") && !element.closest("[hidden]"));
    (focusable()[0] ?? dialog.current)?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); if (!busy.current) close.current(); }
      if (event.key !== "Tab") return;
      const targets = focusable();
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first || !last) { event.preventDefault(); dialog.current?.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !dialog.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [host]);
  const [saving, setSaving] = useState(false);
  if (!host) return null;
  return createPortal(<div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-3 sm:p-6">
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby={headingId} tabIndex={-1} className="flex max-h-[94dvh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl dark:bg-gray-900">
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-gray-700">
        <h2 id={headingId} className="text-lg font-semibold">Add Integration</h2>
        <button type="button" aria-label="Close Add Integration" title="Close" disabled={saving} onClick={() => { if (!busy.current) onClose(); }} className="rounded p-2 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800"><X size={20} /></button>
      </div>
      <div className="min-h-0 overflow-y-auto p-4 sm:p-6">
        <CreateToolForm context={{ kind: "workflow", teamId }} onCreated={onCreated} onCancel={() => { if (!busy.current) onClose(); }} onBusyChange={(value) => { busy.current = value; setSaving(value); }} />
      </div>
    </div>
  </div>, host);
}
