"use client";

import { useRef, useState } from "react";
import { buildApiUrl } from "@/lib/api";
import type { KnowledgeVideo } from "@/lib/product-presentations";

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

function VideoCard({ video, locale }: { video: KnowledgeVideo; locale: "th" | "en" }) {
  const player = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const english = locale === "en";
  const warnings = videoWarnings(video, locale);
  return <article className="min-w-0 space-y-3 rounded-xl border border-gray-200 bg-white/60 p-3 dark:border-gray-700 dark:bg-gray-900/50">
    <div><h4 className="break-words text-sm font-medium">{video.title}</h4><div className="break-words text-xs text-gray-500">{video.source_label}</div></div>
    {failed ? <p role="status" className="text-sm">{english ? "Video unavailable. Search again to refresh access." : "วิดีโอไม่พร้อมใช้งาน กรุณาค้นหาใหม่"}</p> : <video ref={player} src={buildApiUrl(video.video_url)} poster={video.poster_url ? buildApiUrl(video.poster_url) : undefined} controls playsInline preload="metadata" aria-label={video.title} className="max-h-80 w-full rounded-lg bg-black" onError={() => setFailed(true)} />}
    <div className="text-xs text-gray-500">{english ? "Analyzed sampled frames" : "วิเคราะห์จากภาพตัวอย่าง"} · {video.time_basis === "frame_order" ? (english ? "Time unknown · frame order" : "ไม่ทราบเวลา · แสดงลำดับเฟรม") : (english ? "Time within clip" : "เวลาภายในคลิป")}</div>
    {video.events.length > 0 && <ol className="max-h-80 space-y-3 overflow-y-auto" aria-label={english ? "Observed events" : "เหตุการณ์ที่พบ"}>{video.events.map((event, index) => <li key={event.event_id} className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800">
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500"><span>{english ? "Event" : "เหตุการณ์"} {index + 1}</span>{event.start_ms !== null ? <button type="button" disabled={failed} className="rounded px-1 text-blue-700 underline disabled:opacity-50" onClick={() => { if (player.current && event.start_ms !== null) { player.current.currentTime = event.start_ms / 1000; void player.current.play().catch(() => undefined); } }} aria-label={`${english ? "Play at" : "เล่นที่"} ${videoPosition(event.start_ms)}`}>{videoPosition(event.start_ms)}{event.end_ms !== null && event.end_ms !== event.start_ms ? `–${videoPosition(event.end_ms)}` : ""}</button> : <span>{english ? "Frames" : "เฟรม"} {event.start_frame + 1}–{event.end_frame + 1}</span>}</div>
      <p className="mt-1 whitespace-pre-wrap break-words text-sm">{event.description}</p>
      {event.frames.length > 0 && <details className="mt-2 text-xs"><summary className="cursor-pointer">{english ? "Evidence frames" : "ภาพอ้างอิง"} ({event.frames.length})</summary><div className="mt-2 flex gap-2 overflow-x-auto">{event.frames.map((frame) => <figure key={frame.frame_index} className="w-32 shrink-0"><a href={buildApiUrl(frame.image_url)} target="_blank" rel="noreferrer"><img src={buildApiUrl(frame.image_url)} loading="lazy" className="h-24 w-32 rounded object-contain" alt={`${english ? "Frame" : "เฟรม"} ${frame.frame_index + 1}`} /></a><figcaption>{frame.offset_ms !== null ? videoPosition(frame.offset_ms) : `${english ? "Frame" : "เฟรม"} ${frame.frame_index + 1}`}</figcaption></figure>)}</div></details>}
    </li>)}</ol>}
    <details className="text-xs text-gray-500"><summary className="cursor-pointer">{english ? "Analysis coverage" : "ขอบเขตการวิเคราะห์"}</summary><p className="mt-2">{english ? "Sampled frames may miss brief events. Clip time is not CCTV clock time." : "ภาพตัวอย่างอาจไม่ครอบคลุมเหตุการณ์สั้น ๆ เวลาภายในคลิปไม่ใช่เวลานาฬิกาของกล้อง"}</p>{!video.complete && <p className="mt-1">{english ? "Only part of this clip was analyzed." : "วิเคราะห์ได้เพียงบางส่วนของคลิป"}</p>}{warnings.length > 0 && <ul className="mt-1 list-inside list-disc">{warnings.map((warning, index) => <li key={index} className="break-words">{warning}</li>)}</ul>}</details>
  </article>;
}

export function KnowledgeVideos({ videos, locale = "th" }: { videos: KnowledgeVideo[]; locale?: "th" | "en" }) {
  if (!videos.length) return null;
  return <section aria-label={locale === "en" ? "Video references" : "วิดีโออ้างอิง"} className="min-w-0 space-y-3">{videos.map(video => <VideoCard key={video.asset_id} video={video} locale={locale} />)}</section>;
}
