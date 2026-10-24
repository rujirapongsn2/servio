"use client";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
export default function WorkflowPanelDialog({ title, onClose, children, busy = false, onChildClose }: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  busy?: boolean;
  onChildClose?: () => void;
}) {
  const heading = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const locked = useRef(busy);
  close.current = onClose;
  locked.current = busy;
  const closeChild = useRef(onChildClose);
  closeChild.current = onChildClose;
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setHost(document.body);
  }, []);
  useEffect(() => {
    if (!host)
      return;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    const topDialog = () => Array.from(document.body.querySelectorAll<HTMLElement>('[role="dialog"]')).at(-1) ?? dialog.current;
    const key = (event: KeyboardEvent) => {
      if (event.defaultPrevented || (event.target instanceof HTMLElement && event.target.closest("dialog[open]")))
        return;
      const scope = topDialog();
      if (!scope?.contains(event.target instanceof Node ? event.target : null))
        return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!locked.current && scope.getAttribute("aria-busy") !== "true") {
          if (scope !== dialog.current && closeChild.current)
            closeChild.current();
          else
            close.current();
        }
      }
      if (event.key !== "Tab")
        return;
      const targets = Array.from(scope.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')).filter(item => !item.closest("fieldset:disabled") && !item.closest("[hidden]"));
      const first = targets[0], last = targets[targets.length - 1];
      if (!first || !last) {
        event.preventDefault();
        scope.focus();
      }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === scope)) {
        event.preventDefault();
        last.focus();
      }
      else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    let lastScope: HTMLElement | null = dialog.current;
    const observer = new MutationObserver(() => {
      const scope = topDialog();
      if (!scope || lastScope === scope)
        return;
      lastScope = scope;
      if (!scope.hasAttribute("tabindex"))
        scope.tabIndex = -1;
      (scope.querySelector<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled)') ?? scope).focus();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("keydown", key);
    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, [host]);
  if (!host)
    return null;
  return createPortal(<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-5">
  <div ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={heading} className="flex max-h-[96dvh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white text-gray-900 shadow-xl dark:bg-gray-900 dark:text-white">
  <header className="flex shrink-0 items-center justify-between gap-3 border-b p-4 dark:border-gray-700">
  <h2 id={heading} className="truncate text-lg font-semibold">{title}</h2>
  <button type="button" onClick={onClose} disabled={busy} aria-label={`Close ${title}`} title="Close" className="rounded p-2 hover:bg-gray-100 disabled:opacity-50 dark:hover:bg-gray-800">
  <X size={20}/>
  </button>
  </header>
  <div className="min-h-0 overflow-y-auto p-4">{children}</div>
  </div>
  </div>, host);
}
