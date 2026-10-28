"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Video, X, Loader2, Send } from "lucide-react";
import { buildApiUrl } from "@/lib/api";
import { parseVideoAttachmentJob, videoUploadIssue, type VideoAttachmentJob } from "@/lib/video-attachments";
import { KnowledgeVideos } from "@/components/KnowledgeVideos";

type State = { kind: "idle" } | { kind: "uploading"; name: string } | { kind: "job"; name: string; job: VideoAttachmentJob } | { kind: "error"; message: string };
type Props = { token: string | null; disabled: boolean; locale?: "th" | "en"; onInquire: (attachmentId: string, query: string) => boolean; onBusyChange?: (busy: boolean) => void };

export function VideoAttachmentComposer({ token, disabled, locale = "th", onInquire, onBusyChange }: Props) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("troubleshooting");
  const [sendError, setSendError] = useState(false);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentJob = useRef<string | null>(null);
  const busyCallback = useRef(onBusyChange);
  busyCallback.current = onBusyChange;
  const id = useId();
  const english = locale === "en";
  const hasToken = token !== null;
  const busy = state.kind === "uploading" || (state.kind === "job" && (state.job.status === "queued" || state.job.status === "processing"));
  useEffect(() => { busyCallback.current?.(busy); return () => busyCallback.current?.(false); }, [busy]);
  useEffect(() => {
    setState({ kind: "idle" }); setQuery(""); setSendError(false); currentJob.current = null;
    return () => { generation.current += 1; controller.current?.abort(); if (timer.current) clearTimeout(timer.current); };
  }, [hasToken]);

  async function cancel() {
    generation.current += 1; controller.current?.abort(); if (timer.current) clearTimeout(timer.current);
    const attachmentId = currentJob.current; currentJob.current = null;
    setState({ kind: "idle" }); setQuery(""); setSendError(false);
    if (attachmentId && token) { try { await fetch(buildApiUrl(`/api/video-attachments/${attachmentId}`), { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }); } catch { /* Expired jobs are cleaned up by the server. */ } }
  }
  async function upload(file: File) {
    if (!token || disabled || busy) return;
    const issue = videoUploadIssue(file);
    if (issue) { setState({ kind: "error", message: issue === "type" ? (english ? "Choose MP4, MOV or WebM." : "เลือกไฟล์ MP4, MOV หรือ WebM") : (english ? "Choose a non-empty video up to 50 MB." : "เลือกวิดีโอขนาดไม่เกิน 50 MB และมีข้อมูล") }); return; }
    void cancel();
    const revision = ++generation.current;
    const abort = new AbortController(); controller.current = abort;
    setState({ kind: "uploading", name: file.name });
    const headers = { Authorization: `Bearer ${token}` };
    async function receive(response: Response) {
      if (!response.ok) throw new Error(english ? "Video processing unavailable. Try again." : "ประมวลผลวิดีโอไม่สำเร็จ กรุณาลองใหม่");
      const value: unknown = await response.json();
      const job = parseVideoAttachmentJob(value);
      if (revision !== generation.current) return;
      if (currentJob.current && currentJob.current !== job.attachment_id) throw new Error("Video job changed");
      currentJob.current = job.attachment_id;
      setState({ kind: "job", name: file.name, job });
      if (job.status === "queued" || job.status === "processing") timer.current = setTimeout(() => { void poll(job.attachment_id); }, 1200);
    }
    async function poll(attachmentId: string) {
      if (revision !== generation.current) return;
      try { await receive(await fetch(buildApiUrl(`/api/video-attachments/${attachmentId}`), { headers, signal: abort.signal })); }
      catch (error) { if (revision === generation.current && !abort.signal.aborted) setState({ kind: "error", message: error instanceof Error ? error.message : (english ? "Unable to check video status." : "ตรวจสอบสถานะวิดีโอไม่สำเร็จ") }); }
    }
    try { const body = new FormData(); body.append("file", file); await receive(await fetch(buildApiUrl("/api/video-attachments"), { method: "POST", headers, body, signal: abort.signal })); }
    catch (error) { if (revision === generation.current && !abort.signal.aborted) setState({ kind: "error", message: error instanceof Error ? error.message : (english ? "Video upload failed." : "อัปโหลดวิดีโอไม่สำเร็จ") }); }
  }
  if (!token) return null;
  const readyJob = state.kind === "job" && state.job.status === "ready" ? state.job : null;
  return <section className="max-h-[55dvh] min-h-0 min-w-0 shrink-0 space-y-2 overflow-y-auto px-3 pt-2" aria-label={english ? "Ask about a video" : "ถามเกี่ยวกับวิดีโอ"}>
    {state.kind === "idle" || state.kind === "error" ? <label className={`inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white/70 px-3 py-1.5 text-sm text-blue-700 ${disabled ? "opacity-50" : "cursor-pointer hover:bg-blue-50"}`}><Video size={16} aria-hidden="true" />{english ? "Attach video" : "แนบวิดีโอ"}<input type="file" aria-label={english ? "Attach video, up to 50 MB" : "แนบวิดีโอ ไม่เกิน 50 MB"} accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" className="sr-only" disabled={disabled} onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) void upload(file); }} /></label> : <div className="flex min-w-0 items-center gap-2 text-sm"><Video size={16} className="shrink-0" /><span className="min-w-0 flex-1 truncate">{state.name}</span><button type="button" onClick={() => void cancel()} aria-label={english ? "Remove video" : "นำวิดีโอออก"} title={english ? "Remove video" : "นำวิดีโอออก"} className="rounded p-1 hover:bg-gray-100"><X size={16} /></button></div>}
    {busy && <div role="status" className="flex items-center gap-2 text-xs text-gray-500"><Loader2 size={14} className="animate-spin motion-reduce:animate-none" />{state.kind === "uploading" ? (english ? "Uploading video…" : "กำลังอัปโหลดวิดีโอ…") : (english ? "Analyzing video frames…" : "กำลังวิเคราะห์ภาพในวิดีโอ…")}</div>}
    {state.kind === "error" && <p role="alert" className="text-sm text-red-600">{state.message}</p>}
    {state.kind === "job" && ["failed", "cancelled", "expired"].includes(state.job.status) && <p role="alert" className="text-sm text-red-600">{state.job.message || (english ? "Video unavailable. Remove it and upload again." : "วิดีโอไม่พร้อมใช้งาน กรุณานำออกและอัปโหลดใหม่")}</p>}
    {readyJob && <form className="space-y-2 rounded-xl border border-blue-100 bg-white/60 p-3" onSubmit={event => { event.preventDefault(); const question = query.trim() || (mode === "events" ? (english ? "Describe the observed events in order and their evidence. If time is unknown, use frame order." : "มีเหตุการณ์อะไรเกิดขึ้นบ้าง เรียงตามลำดับพร้อมหลักฐาน หากไม่ทราบเวลาให้ระบุลำดับเฟรม") : (english ? "What problem is visible in this video? Use the connected knowledge for troubleshooting and distinguish observations from possible causes." : "วิดีโอนี้พบปัญหาอะไร ใช้แหล่งความรู้ที่เชื่อมไว้ช่วยแนะนำการแก้ไข โดยแยกสิ่งที่เห็นกับสาเหตุที่เป็นไปได้")); setSendError(!onInquire(readyJob.attachment_id, question)); }}>
      <div className="flex flex-wrap items-center gap-2"><label htmlFor={`${id}-mode`} className="text-xs">{english ? "Question type" : "ประเภทคำถาม"}</label><select id={`${id}-mode`} value={mode} disabled={disabled} onChange={event => setMode(event.target.value)} className="min-w-0 rounded border border-gray-200 bg-white px-2 py-1 text-xs"><option value="troubleshooting">{english ? "Troubleshooting" : "ปัญหาการใช้งาน"}</option><option value="events">{english ? "Events / CCTV" : "เหตุการณ์ / CCTV"}</option></select></div>
      <label htmlFor={`${id}-query`} className="block text-sm">{english ? "Video question" : "คำถามเกี่ยวกับวิดีโอ"}</label><div className="flex gap-2"><textarea id={`${id}-query`} rows={2} maxLength={2000} value={query} disabled={disabled} onChange={event => { setQuery(event.target.value); setSendError(false); }} placeholder={english ? "Optional — uses the selected question type" : "เว้นว่างเพื่อถามตามประเภทที่เลือก"} className="min-w-0 flex-1 resize-y rounded-lg border border-gray-200 bg-white p-2 text-sm" /><button type="submit" disabled={disabled} className="self-end rounded-lg bg-blue-600 p-2 text-white disabled:opacity-50" aria-label={english ? "Ask about video" : "ถามเกี่ยวกับวิดีโอ"}><Send size={18} /></button></div>
      {sendError && <p role="alert" className="text-sm text-red-600">{english ? "Unable to send. Reconnect and try again." : "ส่งคำถามไม่สำเร็จ กรุณาเชื่อมต่อแล้วลองใหม่"}</p>}
      {readyJob.presentation && <details className="text-xs"><summary className="cursor-pointer text-blue-700">{english ? "Video evidence" : "ดูวิดีโอและภาพอ้างอิง"}</summary><div className="mt-2"><KnowledgeVideos videos={readyJob.presentation.videos} locale={locale} /></div></details>}
    </form>}
  </section>;
}
