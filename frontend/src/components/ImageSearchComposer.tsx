"use client";

import { useEffect, useRef, useState } from "react";
import { ImagePlus, Send, X } from "lucide-react";
import type { ImageSearchState } from "@/hooks/useWebsocket";

type ImageDraft =
  | { kind: "empty" }
  | { kind: "validating" }
  | { kind: "ready"; file: File; preview: string; mime: "image/jpeg" | "image/png" }
  | { kind: "encoding"; file: File; preview: string; mime: "image/jpeg" | "image/png" }
  | { kind: "submitted"; file: File; preview: string; mime: "image/jpeg" | "image/png" };

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("อ่านรูปภาพไม่สำเร็จ กรุณาลองใหม่"));
    reader.onload = () => typeof reader.result === "string" ? resolve(reader.result.split(",", 2)[1]) : reject(new Error("อ่านรูปภาพไม่สำเร็จ"));
    reader.readAsDataURL(file);
  });
}

async function checkImage(file: File, preview: string) {
  if (!file.size || file.size > 10 * 1024 * 1024 || !["image/jpeg", "image/png"].includes(file.type)) throw new Error("ใช้รูป JPG หรือ PNG ขนาดไม่เกิน 10 MB");
  await new Promise<void>((resolve, reject) => {
    const image = new Image();
    image.onload = () => image.naturalWidth * image.naturalHeight <= 20_000_000 ? resolve() : reject(new Error("ใช้รูปภาพขนาดไม่เกิน 20 ล้านพิกเซล"));
    image.onerror = () => reject(new Error("รูปภาพไม่ถูกต้อง กรุณาใช้ JPG หรือ PNG"));
    image.src = preview;
  });
}

export function ImageSearchComposer({ available, disabled, searchState, onImageSearch, onTextMessage }: {
  available: boolean;
  disabled: boolean;
  searchState: ImageSearchState;
  onImageSearch: (image: { mime: "image/jpeg" | "image/png"; base64: string }, query?: string) => boolean;
  onTextMessage: (message: string) => void;
}) {
  const [draft, setDraft] = useState<ImageDraft>({ kind: "empty" });
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const version = useRef(0);
  const submitting = useRef<{ selected: Extract<ImageDraft, { kind: "ready" }>; query: string } | null>(null);
  const preview = "preview" in draft ? draft.preview : null;
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => () => { version.current += 1; }, []);
  useEffect(() => {
    if (searchState.kind === "complete") {
      version.current += 1;
      submitting.current = null;
      setDraft({ kind: "empty" });
    } else if (searchState.kind === "error" && submitting.current) {
      const { selected, query } = submitting.current;
      version.current += 1;
      submitting.current = null;
      setText((current) => current || query);
      setDraft(selected);
    }
  }, [searchState]);
  const busy = disabled || draft.kind === "validating" || draft.kind === "encoding" || draft.kind === "submitted" || searchState.kind === "pending";

  async function selectImage(file: File | undefined) {
    if (!file) return;
    const current = ++version.current;
    setError(null);
    setDraft({ kind: "validating" });
    const preview = URL.createObjectURL(file);
    try {
      await checkImage(file, preview);
      if (current !== version.current) { URL.revokeObjectURL(preview); return; }
      if (file.type === "image/jpeg" || file.type === "image/png") setDraft({ kind: "ready", file, preview, mime: file.type });
    } catch (failure) {
      URL.revokeObjectURL(preview);
      if (current !== version.current) return;
      setDraft({ kind: "empty" });
      setError(failure instanceof Error ? failure.message : "รูปภาพไม่ถูกต้อง");
    }
  }

  async function submit() {
    if (busy || submitting.current) return;
    if (draft.kind === "empty") {
      if (text.trim()) { onTextMessage(text.trim()); setText(""); }
      return;
    }
    if (draft.kind !== "ready") return;
    const query = text.trim();
    if (query.length > 2000) { setError("ระบุข้อความเพิ่มเติมไม่เกิน 2,000 ตัวอักษร"); return; }
    const current = version.current;
    const selected = draft;
    submitting.current = { selected, query };
    setDraft({ ...selected, kind: "encoding" });
    setError(null);
    try {
      const base64 = await readFile(selected.file);
      if (version.current !== current) return;
      setDraft({ ...selected, kind: "submitted" });
      if (onImageSearch({ mime: selected.mime, base64 }, query)) {
        setText((value) => value === text ? "" : value);
      } else {
        submitting.current = null;
        if (version.current === current) setDraft(selected);
      }
    } catch (failure) {
      submitting.current = null;
      if (version.current === current) {
        setError(failure instanceof Error ? failure.message : "อ่านรูปภาพไม่สำเร็จ");
        setDraft(selected);
      }
    }
  }

  return <form data-chat-composer className="w-full min-w-0 space-y-2" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
    {preview && <div className="flex items-center gap-3 rounded-xl border border-gray-200 p-2 dark:border-gray-700">
      <img src={preview} alt="รูปภาพที่เลือกค้นหา" className="h-16 w-16 rounded-lg bg-gray-50 object-contain" />
      <div className="min-w-0 flex-1 text-sm"><p className="truncate">{"file" in draft ? draft.file.name : ""}</p><p className="text-xs text-gray-500">ค้นหาสินค้าจากรูปภาพ</p></div>
      <button type="button" title="นำรูปภาพออก" aria-label="นำรูปภาพออก" disabled={busy} className="rounded-full p-2 disabled:opacity-50" onClick={() => { version.current += 1; setDraft({ kind: "empty" }); setError(null); }}><X size={18} /></button>
    </div>}
    <div className="flex min-w-0 items-center gap-2">
      {available && <><input ref={picker} type="file" accept="image/jpeg,image/png" aria-label="แนบรูปภาพ JPG หรือ PNG เพื่อค้นหาสินค้า" className="sr-only" disabled={busy} onChange={(event) => { void selectImage(event.target.files?.[0]); event.target.value = ""; }} /><button type="button" disabled={busy} aria-label={preview ? "เปลี่ยนรูปภาพค้นหา" : "แนบรูปภาพค้นหาสินค้า"} title={preview ? "เปลี่ยนรูปภาพ" : "ค้นหาด้วยรูปภาพ"} className="shrink-0 rounded-full border p-2.5 text-gray-600 disabled:opacity-50 dark:text-gray-200" onClick={() => picker.current?.click()}><ImagePlus size={20} /></button></>}
      <label className="sr-only" htmlFor="widget-chat-message">ข้อความ</label>
      <input id="widget-chat-message" name="message" type="text" value={text} disabled={busy} maxLength={draft.kind === "empty" ? undefined : 2000} onChange={(event) => setText(event.target.value)} placeholder={draft.kind !== "empty" ? "ระบุความต้องการเพิ่มเติม (ไม่บังคับ)" : "พิมพ์ข้อความ…"} className="min-w-0 flex-1 rounded-full border border-gray-200 bg-gray-50 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900" autoComplete="off" />
      <button type="submit" disabled={busy || (draft.kind === "empty" && !text.trim())} aria-label={preview ? "ค้นหาสินค้าจากรูปภาพ" : "ส่งข้อความ"} title={preview ? "ค้นหาจากรูปภาพ" : "ส่งข้อความ"} className="h-10 w-10 shrink-0 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-50"><Send size={18} /></button>
    </div>
    {(draft.kind === "validating" || searchState.kind === "pending") && <p role="status" className="text-xs text-gray-500">{draft.kind === "validating" ? "กำลังตรวจสอบรูปภาพ…" : "กำลังค้นหาสินค้า…"}</p>}
    {(error || searchState.kind === "error") && <p role="alert" className="text-sm text-red-600">{error || (searchState.kind === "error" ? searchState.message : "")}</p>}
  </form>;
}
