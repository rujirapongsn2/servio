"use client";

import { useEffect, useId, useRef, useState } from "react";
import { buildApiUrl } from "@/lib/api";
import type { KnowledgeVideo, KnowledgeVideoEvent } from "@/lib/product-presentations";

export function videoPosition(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function videoWarnings(video: KnowledgeVideo, locale: "th" | "en"): string[] {
  const translations: Record<string, string> = {
    "Audio is not analyzed in hybrid_frames mode. Native video/Metal inference is not enabled.": "รุ่นนี้วิเคราะห์เฉพาะภาพในคลิป ไม่วิเคราะห์เสียง",
    "Frame analysis runs when the video is imported.": "เริ่มวิเคราะห์เมื่อบันทึกแหล่งความรู้",
  };
  return Array.from(new Set(video.warnings.filter(warning =>
    warning !== "Sampled frames may miss short events. Event counts are not exhaustive." &&
    !(!video.complete && warning === "Only a bounded portion was processed; later events may be missing.") &&
    !(video.time_basis === "frame_order" && warning === "Reliable media timestamps unavailable; use frame order only.")
  ).map(warning => locale === "th" ? translations[warning] ?? warning : warning)));
}

function eventLabel(event: KnowledgeVideoEvent, english: boolean): string {
  if (event.start_ms !== null) return `${videoPosition(event.start_ms)}${event.end_ms !== null && event.end_ms > event.start_ms ? `–${videoPosition(event.end_ms)}` : ""}`;
  return `${english ? "Frames" : "ภาพลำดับ"} ${event.start_frame + 1}–${event.end_frame + 1}`;
}

type Playback = { kind: "clip" } | { kind: "range"; start: number; end: number | null };

function VideoViewer({ video, locale, onClose }: { video: KnowledgeVideo; locale: "th" | "en"; onClose: () => void }) {
  const english = locale === "en";
  const titleId = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const [selected, setSelected] = useState(0);
  const [mode, setMode] = useState<"video" | "frames">(video.time_basis === "frame_order" ? "frames" : "video");
  const [failed, setFailed] = useState(false);
  const [finished, setFinished] = useState(false);
  const [playBlocked, setPlayBlocked] = useState(false);
  const playback = useRef<Playback>({ kind: "clip" });
  const pendingSeek = useRef<number | null>(null);
  const event = video.events[selected];
  const warnings = videoWarnings(video, locale);

  useEffect(() => {
    const node = dialog.current;
    if (node && !node.open) node.showModal?.();
    return () => { player.current?.pause(); node?.close?.(); };
  }, []);

  const play = () => {
    const promise = player.current?.play();
    promise?.catch(() => setPlayBlocked(true));
  };
  const seek = (milliseconds: number) => {
    const node = player.current;
    if (!node || node.readyState < 1) { pendingSeek.current = milliseconds; return; }
    node.currentTime = milliseconds / 1000;
    pendingSeek.current = null;
    play();
  };
  const choose = (index: number) => {
    const next = video.events[index];
    setSelected(index); setFinished(false); setPlayBlocked(false);
    if (!next) { playback.current = { kind: "clip" }; setMode("video"); return; }
    if (video.time_basis === "media" && next?.start_ms !== null && next?.start_ms !== undefined) {
      playback.current = { kind: "range", start: next.start_ms, end: next.end_ms !== null && next.end_ms > next.start_ms ? next.end_ms : null };
      setMode("video"); seek(next.start_ms);
    } else {
      player.current?.pause(); playback.current = { kind: "clip" }; pendingSeek.current = null; setMode("frames");
    }
  };
  useEffect(() => { choose(0); }, []);
  useEffect(() => {
    if (mode === "video" && player.current && pendingSeek.current !== null) seek(pendingSeek.current);
  }, [mode]);

  return <dialog ref={dialog} aria-labelledby={titleId} onCancel={onClose} onClose={onClose}
    className="fixed inset-0 m-0 h-[100dvh] max-h-[100dvh] w-full max-w-none overflow-hidden border-0 bg-[#F4FAFD] p-0 text-[#0D1B2A] shadow-2xl backdrop:bg-[#0D1B2A]/35 sm:left-auto sm:ml-auto sm:w-[28rem] sm:border-l sm:border-white/70">
    <div className="flex h-full min-h-0 flex-col bg-gradient-to-br from-white/90 via-sky-50/70 to-emerald-50/50">
      <header className="flex shrink-0 items-start gap-3 border-b border-[#DCE8EF] bg-white/75 p-4">
        <div className="min-w-0 flex-1"><p className="text-xs text-[#52738B]">{english ? "Video reference" : "วิดีโออ้างอิง"}</p><h3 id={titleId} className="break-words text-base font-semibold">{video.title}</h3></div>
        <button type="button" autoFocus onClick={onClose} aria-label={english ? "Back to chat" : "กลับสู่แชต"} className="min-h-10 shrink-0 rounded-lg border border-[#DCE8EF] bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2786C2]">{english ? "Close" : "ปิด"} ×</button>
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full bg-white/80 px-2 py-1 text-[#52738B]">{video.time_basis === "frame_order" ? (english ? "Time unknown · frame order" : "ไม่ทราบเวลา · ใช้ลำดับภาพ") : (english ? "Time within clip" : "เวลาภายในคลิป")}</span>
          <button type="button" onClick={() => { player.current?.pause(); pendingSeek.current = null; playback.current = { kind: "clip" }; setFinished(false); setMode(mode === "video" ? "frames" : "video"); }} className="ml-auto min-h-9 rounded-lg px-2 font-medium text-[#1A5A8A] underline">{mode === "video" ? (english ? "Evidence frames" : "ภาพอ้างอิง") : (english ? "Full video" : "ดูวิดีโอเต็ม")}</button>
        </div>
        {mode === "video" && (failed ? <p role="status" className="rounded-lg bg-white p-3 text-sm">{english ? "Video unavailable. Search again to refresh access." : "วิดีโอไม่พร้อมใช้งาน กรุณาค้นหาใหม่"}</p> : <video ref={player} src={buildApiUrl(video.video_url)} poster={video.poster_url ? buildApiUrl(video.poster_url) : undefined} controls playsInline preload="metadata" aria-label={video.title}
          className="max-h-[42dvh] w-full rounded-xl bg-black"
          onLoadedMetadata={() => { if (pendingSeek.current !== null) seek(pendingSeek.current); }}
          onError={() => { setFailed(true); pendingSeek.current = null; }}
          onTimeUpdate={() => {
            const node = player.current; const range = playback.current;
            if (node && range.kind === "range" && range.end !== null && node.currentTime >= range.end / 1000) {
              node.pause(); node.currentTime = range.end / 1000; setFinished(true); playback.current = { kind: "clip" };
            }
          }}
          onSeeking={() => {
            const node = player.current; const range = playback.current;
            if (node && range.kind === "range" && (node.currentTime < range.start / 1000 - .1 || range.end !== null && node.currentTime > range.end / 1000 + .1)) {
              playback.current = { kind: "clip" }; setFinished(false);
            }
          }} />)}
        {playBlocked && <p role="status" className="text-xs text-[#52738B]">{english ? "Press play on the video to start." : "กดปุ่มเล่นบนวิดีโอเพื่อเริ่มดู"}</p>}
        {finished && <div role="status" className="flex flex-wrap gap-2 rounded-xl bg-white/80 p-2">
          <button type="button" onClick={() => choose(selected)} className="min-h-10 rounded-lg bg-[#2786C2] px-3 text-sm font-medium text-white">{english ? "Replay" : "ดูซ้ำ"}</button>
          <button type="button" onClick={() => { playback.current = { kind: "clip" }; setFinished(false); play(); }} className="min-h-10 rounded-lg border border-[#DCE8EF] px-3 text-sm">{english ? "Continue full clip" : "ดูต่อทั้งคลิป"}</button>
        </div>}
        {mode === "frames" && <div className="space-y-3" aria-label={english ? "Evidence frames" : "ภาพอ้างอิง"}>
          {(event?.frames.length ?? 0) > 0 ? event.frames.map(frame => <figure key={frame.frame_index} className="overflow-hidden rounded-xl border border-white bg-white/80">
            <img src={buildApiUrl(frame.image_url)} loading="lazy" className="max-h-[40dvh] w-full object-contain" alt={`${english ? "Evidence frame" : "ภาพอ้างอิงลำดับ"} ${frame.frame_index + 1}`} />
            <figcaption className="px-3 py-2 text-xs text-[#52738B]">{english ? "Frame" : "ภาพลำดับ"} {frame.frame_index + 1}{frame.offset_ms !== null && video.time_basis === "media" && <button type="button" onClick={() => { playback.current = { kind: "clip" }; setMode("video"); if (frame.offset_ms !== null) seek(frame.offset_ms); }} className="ml-3 min-h-9 text-[#1A5A8A] underline">▶ {videoPosition(frame.offset_ms)}</button>}</figcaption>
          </figure>) : <p className="rounded-xl bg-white/80 p-3 text-sm text-[#52738B]">{english ? "No reference frames for this section." : "ไม่มีภาพอ้างอิงสำหรับส่วนนี้"}</p>}
        </div>}
        {video.events.length > 0 && <section aria-label={english ? "Referenced sections" : "ช่วงอ้างอิง"} className="space-y-2">
          <h4 className="text-sm font-semibold">{english ? "Referenced sections" : "ช่วงอ้างอิง"}</h4>
          {video.events.map((item, index) => <button key={item.event_id} type="button" aria-pressed={index === selected} onClick={() => choose(index)} className={`block w-full rounded-xl border p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2786C2] ${index === selected ? "border-[#2786C2]/60 bg-sky-100/60" : "border-white bg-white/70"}`}>
            <span className="text-xs font-semibold text-[#1A5A8A]">{item.start_ms !== null && video.time_basis === "media" ? "▶ " : ""}{eventLabel(item, english)}</span>
            <span className="mt-1 block whitespace-pre-wrap break-words text-sm">{item.description}</span>
          </button>)}
        </section>}
        <details className="rounded-xl border border-white/80 bg-white/60 p-3 text-xs text-[#52738B]"><summary className="cursor-pointer">{english ? "Source and coverage" : "แหล่งที่มาและขอบเขต"}</summary>
          <p className="mt-2 break-words">{video.source_label}</p>
          <p className="mt-2">{english ? "Sampled frames may miss brief events. Clip time is not CCTV clock time." : "ภาพตัวอย่างอาจไม่ครอบคลุมเหตุการณ์สั้น ๆ เวลาภายในคลิปไม่ใช่เวลานาฬิกาของกล้อง"}</p>
          {!video.complete && <p className="mt-1">{english ? "Only part of this clip was analyzed." : "วิเคราะห์ได้เพียงบางส่วนของคลิป"}</p>}
          {warnings.map((warning, index) => <p key={index} className="mt-1 break-words">{warning}</p>)}
        </details>
      </div>
    </div>
  </dialog>;
}

function VideoCard({ video, locale }: { video: KnowledgeVideo; locale: "th" | "en" }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const english = locale === "en";
  const poster = video.poster_url || video.events[0]?.frames[0]?.image_url;
  return <article className="min-w-0 overflow-hidden rounded-2xl border border-white/80 bg-white/70 shadow-sm backdrop-blur-sm">
    <button ref={trigger} type="button" onClick={() => setOpen(true)} aria-label={`${english ? "Open video reference" : "เปิดวิดีโออ้างอิง"} ${video.title}`} className="flex min-h-24 w-full items-center gap-3 p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#2786C2]">
      <span className="relative flex h-16 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-sky-100 to-emerald-50">
        {poster && <img src={buildApiUrl(poster)} alt="" loading="lazy" className="h-full w-full object-cover" />}
        <span aria-hidden="true" className="absolute flex h-8 w-8 items-center justify-center rounded-full bg-[#1A5A8A]/90 text-sm text-white">▶</span>
      </span>
      <span className="min-w-0 flex-1"><span className="block text-[11px] font-medium text-[#52738B]">{english ? "Video reference" : "วิดีโออ้างอิง"}</span><span className="block truncate text-sm font-semibold text-[#0D1B2A]" title={video.title}>{video.title}</span>
        <span className="mt-1 block text-xs font-medium text-[#1A5A8A]">{video.events[0] ? eventLabel(video.events[0], english) : (english ? "View video" : "ดูวิดีโอ")}{video.events.length > 1 ? ` · ${english ? `+${video.events.length - 1} sections` : `อีก ${video.events.length - 1} ช่วง`}` : ""}</span>
        {video.time_basis === "frame_order" && <span className="block text-[11px] text-[#52738B]">{english ? "Time unknown" : "ไม่ทราบเวลา"}</span>}
      </span>
    </button>
    {open && <VideoViewer video={video} locale={locale} onClose={() => { setOpen(false); queueMicrotask(() => trigger.current?.focus()); }} />}
  </article>;
}

export function KnowledgeVideos({ videos, locale = "th" }: { videos: KnowledgeVideo[]; locale?: "th" | "en" }) {
  if (!videos.length) return null;
  return <section aria-label={locale === "en" ? "Video references" : "วิดีโออ้างอิง"} className="min-w-0 space-y-2">{videos.map(video => <VideoCard key={video.asset_id} video={video} locale={locale} />)}</section>;
}
