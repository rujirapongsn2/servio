"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ProductCarousel } from "./ProductCarousel";
import { buildApiUrl } from "@/lib/api";
import { COLOR_OPTIONS, PATTERN_OPTIONS, colorValue, patternValue, type DiscoveryAction, type DiscoveryFilters, type DiscoverySurface } from "@/lib/a2ui-discovery";
import styles from "./ProductDiscovery.module.css";

/** Renderer for ProductDiscovery in Servio's registered A2UI catalog. */
export function ProductDiscovery({ surface, disabled, onAction }: {
  surface: DiscoverySurface; disabled: boolean;
  onAction: (surfaceId: string, action: DiscoveryAction) => boolean;
}) {
  const [filters, setFilters] = useState<DiscoveryFilters>(surface.filters);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [comparing, setComparing] = useState(false);
  const compareDialog = useRef<HTMLDialogElement>(null);
  const compareTrigger = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const colorId = useId();
  const patternId = useId();
  const selected = surface.products.filter(product => selectedIds.includes(product.id));
  const productIds = surface.products.map(product => product.id).join(":");
  const canAct = surface.active && !disabled;
  const filtersChanged = filters.color !== surface.filters.color || filters.pattern !== surface.filters.pattern;
  useEffect(() => { setFilters(surface.filters); }, [surface.filters.color, surface.filters.pattern]);
  useEffect(() => {
    const currentIds = new Set(productIds.split(":"));
    setSelectedIds(ids => ids.filter(id => currentIds.has(id)));
    setComparing(false);
  }, [productIds]);
  useEffect(() => {
    if (comparing) compareDialog.current?.showModal();
    else if (compareDialog.current?.open) compareDialog.current.close();
  }, [comparing]);
  function inquire(cardId: string) {
    if (canAct && onAction(surface.id, { name: "discovery.inquire", context: { card_id: cardId } })) setComparing(false);
  }
  function closeComparison() { setComparing(false); compareTrigger.current?.focus(); }
  return <section className={styles.discovery} data-a2ui-catalog="product-discovery" aria-label="ค้นหาสินค้าจากภาพ">
    <header className={styles.query}>
      <img src={surface.queryImage} alt="ภาพต้นฉบับที่ใช้ค้นหา" width={52} height={52} />
      <div><h2>สินค้าจากภาพของคุณ</h2><p>ลายและสีใกล้เคียง · ยังไม่ยืนยันรุ่นเดียวกันหรือสต็อก</p></div>
    </header>
    <form className={styles.filters} aria-label="ปรับสีและลาย" onSubmit={event => {
      event.preventDefault();
      if (canAct && filtersChanged) onAction(surface.id, { name: "discovery.refine", context: filters });
    }}>
      <div><label htmlFor={colorId}>โทนสี</label><select id={colorId} value={filters.color} disabled={!canAct} onChange={event => { const color = colorValue(event.target.value); if (color) setFilters(current => ({ ...current, color })); }}>{COLOR_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
      <div><label htmlFor={patternId}>ลวดลาย</label><select id={patternId} value={filters.pattern} disabled={!canAct} onChange={event => { const pattern = patternValue(event.target.value); if (pattern) setFilters(current => ({ ...current, pattern })); }}>{PATTERN_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
      <button type="submit" disabled={!canAct || !filtersChanged}>{disabled && surface.active ? "กำลังทำงาน…" : "ปรับผลค้นหา"}</button>
    </form>
    {!surface.active && <p className={styles.muted}>ภาพนี้เป็นผลค้นหาก่อนหน้า แนบภาพอีกครั้งเพื่อปรับการค้นหา</p>}
    <p className={styles.summary} role="status" aria-live="polite">{surface.summary}</p>
    {surface.products.length > 0 && <ProductCarousel presentation={{ type: "knowledge_product_carousel", version: 1, summary: "", products: surface.products }}
      disabled={!canAct} onInquire={inquire} selection={{ ids: selected.map(product => product.id), onToggle: id => setSelectedIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : ids.length < 3 ? [...ids, id] : ids) }} />}
    {surface.products.length > 1 && <div className={styles.compareBar}>
      <span>เลือก {selected.length}/3 รายการ</span>
      {selected.length > 0 && <button type="button" onClick={() => setSelectedIds([])}>ล้าง</button>}
      <button ref={compareTrigger} type="button" className={styles.primary} disabled={selected.length < 2} onClick={() => setComparing(true)}>เปรียบเทียบ{selected.length >= 2 ? ` (${selected.length})` : ""}</button>
    </div>}
    <dialog ref={compareDialog} className={styles.dialog} aria-labelledby={titleId} onCancel={closeComparison} onClose={closeComparison}>
      <header className={styles.dialogHeader}><h2 id={titleId}>เปรียบเทียบสินค้า</h2><button type="button" autoFocus onClick={closeComparison} aria-label="ปิดการเปรียบเทียบ">ปิด ×</button></header>
      <p className={styles.muted}>ข้อมูลจากแค็ตตาล็อก · สีบนจออาจต่างจากสินค้าจริง · ยังไม่ยืนยันสต็อก</p>
      <div className={styles.comparison}>
        {selected.map(product => <article key={product.id}>
          <img src={buildApiUrl(product.image_url)} alt={product.title} />
          <h3>{product.title}</h3>
          <dl><dt>รหัสสินค้า</dt><dd>{product.part_number || "ไม่ระบุ"}</dd>{product.brand && <><dt>แบรนด์</dt><dd>{product.brand}</dd></>}<dt>ประเภท</dt><dd>{surface.facets[product.id]?.category || "ไม่ระบุ"}</dd><dt>สีในแค็ตตาล็อก</dt><dd>{surface.facets[product.id]?.color || "ไม่ระบุ"}</dd><dt>ลวดลาย</dt><dd>{surface.facets[product.id]?.pattern || "ไม่ระบุ"}</dd><dt>ลักษณะที่พบ</dt><dd>{product.description || "ไม่ระบุ"}</dd></dl>
          <button type="button" className={styles.primary} disabled={!canAct} onClick={() => inquire(product.id)}>สอบถามสินค้านี้</button>
        </article>)}
      </div>
    </dialog>
  </section>;
}
