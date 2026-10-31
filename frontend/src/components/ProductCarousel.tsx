"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { buildApiUrl } from "@/lib/api";
import { Product, ProductCarouselPresentation, KnowledgeProduct, KnowledgeProductCarouselPresentation } from "@/lib/product-presentations";

type CarouselProduct = Product | KnowledgeProduct;

function ProductImage({ product }: { product: CarouselProduct }) {
  const [failed, setFailed] = useState(false);
  return <div className="aspect-[4/3] shrink-0 bg-gray-50 dark:bg-gray-900 flex items-center justify-center overflow-hidden rounded-t-xl">
    {product.image_url && !failed ? <img src={"asset_id" in product && product.image_url ? buildApiUrl(product.image_url) : product.image_url} alt={product.title} referrerPolicy="no-referrer" loading="lazy" onError={() => setFailed(true)} className="w-full h-full object-contain p-3" /> : <span className="text-sm text-gray-500 px-4">{"asset_id" in product ? "ภาพหมดอายุ กรุณาค้นหาใหม่" : "ไม่มีรูปสินค้า"}</span>}
  </div>;
}

export function ProductCarousel({ presentation, onInquire, disabled, selection }: {
  presentation: ProductCarouselPresentation | KnowledgeProductCarouselPresentation;
  onInquire: (productId: string) => void;
  disabled: boolean;
  selection?: { ids: string[]; onToggle: (id: string) => void };
}) {
  const rail = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const [selected, setSelected] = useState<CarouselProduct | null>(null);
  const titleId = useId();
  const railId = useId();
  useEffect(() => {
    if (selected) dialog.current?.showModal();
  }, [selected]);
  function trapFocus(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== "Tab") return;
    const controls = event.currentTarget.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]");
    const first = controls[0];
    const last = controls[controls.length - 1];
    const active = event.currentTarget.ownerDocument.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first?.focus();
    }
  }
  function closeDetails() {
    dialog.current?.close();
    setSelected(null);
    returnFocus.current?.focus();
  }
  return <section className="w-full min-w-0 max-w-full text-gray-900 dark:text-gray-100" aria-label="สินค้าที่พบ">
    <p className="mb-3 whitespace-pre-wrap break-words text-sm">{presentation.summary}</p>
    <div className="flex items-center justify-between gap-2 mb-2">
      <span className="text-xs text-gray-500">{presentation.products.length} รายการ</span>
      {presentation.products.length > 1 && <div className="flex gap-2">
        <button type="button" aria-label="สินค้าก่อนหน้า" aria-controls={railId} className="rounded-full border px-3 py-1 focus-visible:ring-2 focus-visible:ring-blue-500" onClick={() => rail.current?.scrollBy({ left: -280, behavior: "smooth" })}>‹</button>
        <button type="button" aria-label="สินค้าถัดไป" aria-controls={railId} className="rounded-full border px-3 py-1 focus-visible:ring-2 focus-visible:ring-blue-500" onClick={() => rail.current?.scrollBy({ left: 280, behavior: "smooth" })}>›</button>
      </div>}
    </div>
    <div id={railId} ref={rail} tabIndex={0} role="region" aria-label="เลื่อนดูสินค้า" className="flex gap-3 overflow-x-auto overscroll-x-contain snap-x snap-mandatory pb-3 focus-visible:outline-blue-500">
      {presentation.products.map((product) => <article key={product.id} className="w-[260px] max-w-[85%] shrink-0 snap-start flex flex-col rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
        <ProductImage product={product} />
        <div className="p-3 flex flex-col gap-2 flex-1 min-w-0">
          {selection && <label className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={selection.ids.includes(product.id)} disabled={!selection.ids.includes(product.id) && selection.ids.length >= 3} onChange={() => selection.onToggle(product.id)} aria-label={`เลือกเปรียบเทียบ ${product.title}`} />เปรียบเทียบ</label>}
          <h3 className="text-sm font-semibold break-words line-clamp-2">{product.title}</h3>
          {product.part_number && <div className="font-mono text-sm break-all">{"asset_id" in product ? `รหัส ${product.part_number}` : product.part_number}</div>}
          {product.brand && <div className="text-xs text-gray-500 break-words">{product.brand}</div>}
          {product.price_text && <div className="text-sm font-semibold break-words">{product.price_text}</div>}
          <div className="mt-auto pt-2 flex flex-col gap-2">
            <button type="button" className="rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-blue-500" onClick={(event) => { returnFocus.current = event.currentTarget; setSelected(product); }} aria-label={`ดูรายละเอียด ${product.title}`}>ดูรายละเอียด</button>
            <button type="button" className="rounded-lg bg-blue-600 text-white px-3 py-2 text-sm disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-blue-500" disabled={disabled} onClick={() => onInquire(product.id)} aria-label={`สอบถามสินค้านี้ ${product.title}`}>สอบถามสินค้านี้</button>
          </div>
        </div>
      </article>)}
    </div>
    <dialog ref={dialog} aria-labelledby={titleId} onKeyDown={trapFocus} onCancel={(event) => { event.preventDefault(); closeDetails(); }} onClose={() => { setSelected(null); returnFocus.current?.focus(); }} className="m-auto w-[calc(100%_-_2rem)] max-w-lg max-h-[85dvh] overflow-y-auto rounded-2xl p-0 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 backdrop:bg-black/40">
      {selected && <div className="p-5">
        <div className="flex items-start gap-4 justify-between mb-4"><h2 id={titleId} className="font-semibold break-words min-w-0">{selected.title}</h2><button type="button" autoFocus aria-label="ปิดรายละเอียดสินค้า" className="shrink-0 rounded-lg border px-3 py-1" onClick={closeDetails}>ปิด</button></div>
        <ProductImage key={selected.id} product={selected} />
        {"source_label" in selected && <p className="mt-4 text-xs text-gray-500 break-words">ไฟล์ต้นฉบับ: {selected.source_label}</p>}
        <dl className="mt-4 text-sm space-y-2">{selected.part_number && <div><dt className="text-gray-500">{"asset_id" in selected ? "รหัสสินค้า / สี" : "รหัสสินค้า"}</dt><dd className="break-all">{selected.part_number}</dd></div>}{selected.brand && <div><dt className="text-gray-500">ยี่ห้อ</dt><dd>{selected.brand}</dd></div>}{selected.price_text && <div><dt className="text-gray-500">ราคา</dt><dd>{selected.price_text}</dd></div>}</dl>
        {selected.description && <p className="mt-4 text-sm whitespace-pre-wrap break-words">{selected.description}</p>}
        {selected.detail_url && <a href={selected.detail_url} target="_blank" rel="noopener noreferrer" className="block mt-4 text-blue-600 underline text-sm">เปิดหน้าสินค้า</a>}
        <button type="button" disabled={disabled} className="mt-4 w-full rounded-lg bg-blue-600 text-white px-3 py-2 text-sm disabled:opacity-50" onClick={() => { onInquire(selected.id); closeDetails(); }}>สอบถามสินค้านี้</button>
      </div>}
    </dialog>
  </section>;
}
