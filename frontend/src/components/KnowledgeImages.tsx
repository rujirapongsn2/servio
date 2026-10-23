"use client";
import { useRef, useState } from "react";
import { buildApiUrl } from "@/lib/api";
import type { KnowledgeImage } from "@/lib/product-presentations";

export function KnowledgeImages({ images }: { images: KnowledgeImage[] }) {
  const [selected, setSelected] = useState<KnowledgeImage | null>(null);
  const [failed, setFailed] = useState<string[]>([]);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  function close() { dialog.current?.close(); setSelected(null); trigger.current?.focus(); }
  if (images.length === 0) return null;
  return <section aria-label="รูปภาพอ้างอิง" className="min-w-0 space-y-2">
    <div className="text-sm font-medium">รูปภาพอ้างอิง</div>
    <div className="flex gap-3 overflow-x-auto pb-2">
      {images.map((image) => <article key={image.asset_id} className="w-56 shrink-0 overflow-hidden rounded-xl border border-gray-200 dark:border-gray-700">
        <button type="button" className="block w-full text-left focus-visible:outline-emerald-500" aria-label={`ดูภาพต้นฉบับ ${image.title}`} onClick={(event) => { trigger.current = event.currentTarget; setSelected(image); dialog.current?.showModal(); }}>
          {failed.includes(image.asset_id) ? <div className="flex h-40 items-center justify-center text-sm">ภาพหมดอายุ กรุณาค้นหาใหม่</div> : <img src={buildApiUrl(image.image_url)} alt={image.title} referrerPolicy="no-referrer" loading="lazy" className="h-40 w-full bg-gray-50 object-contain" onError={() => setFailed((old) => [...old, image.asset_id])} />}
          <div className="space-y-1 p-3"><div className="truncate font-medium">{image.title}</div><div className="truncate text-xs text-gray-500">{image.source_label}</div><div className="text-sm text-emerald-700">ดูภาพต้นฉบับ</div></div>
        </button>
      </article>)}
    </div>
    <dialog ref={dialog} onCancel={(event) => { event.preventDefault(); close(); }} onKeyDown={(event) => { if (event.key === "Tab") { event.preventDefault(); dialog.current?.querySelector<HTMLButtonElement>("button")?.focus(); } }} className="m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-4xl rounded-xl bg-white p-4 text-gray-900 shadow-xl backdrop:bg-black/60 dark:bg-gray-900 dark:text-white" aria-label={selected?.title || "ภาพต้นฉบับ"}>
      <div className="mb-3 flex items-center justify-between gap-4"><div className="min-w-0 truncate font-medium">{selected?.title}</div><button type="button" onClick={close} autoFocus className="rounded px-3 py-2" aria-label="ปิดภาพต้นฉบับ">ปิด</button></div>
      {selected && <>{failed.includes(selected.asset_id) ? <p role="status" className="py-8 text-center text-sm">ภาพหมดอายุ กรุณาค้นหาใหม่</p> : <img src={buildApiUrl(selected.image_url)} alt={selected.title} referrerPolicy="no-referrer" className="max-h-[70dvh] w-full object-contain" onError={() => setFailed((old) => [...old, selected.asset_id])} />}<div className="mt-2 truncate text-xs text-gray-500">{selected.source_label}</div></>}
    </dialog>
  </section>;
}
