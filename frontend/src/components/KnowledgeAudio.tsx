"use client";
import { useRef, useState } from "react";
import { buildApiUrl } from "@/lib/api";
import type { KnowledgeAudioClip } from "@/lib/product-presentations";

export function audioTimestamp(milliseconds: number) {
  return `${Math.floor(milliseconds / 60000)}:${String(Math.floor(milliseconds / 1000) % 60).padStart(2, "0")}`;
}

function AudioClip({ clip }: { clip: KnowledgeAudioClip }) {
  const player = useRef<HTMLAudioElement>(null);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  function seek() {
    const element = player.current;
    if (element) {
      element.currentTime = clip.start_ms / 1000;
      void element.play().catch(() => setFailed(true));
    }
  }
  return <article className="min-w-0 space-y-2 rounded-xl border border-gray-200 p-3 dark:border-gray-700">
    <div className="flex min-w-0 items-center justify-between gap-3">
      <div className="min-w-0"><div className="truncate text-sm font-medium">{clip.title}</div><div className="truncate text-xs text-gray-500">{clip.source_label}</div></div>
      <button type="button" disabled={!ready || failed} onClick={seek} aria-label={`เล่น ${clip.title} ที่ ${audioTimestamp(clip.start_ms)}`} className="shrink-0 rounded px-2 py-1 text-sm text-emerald-700 disabled:opacity-50">{audioTimestamp(clip.start_ms)}–{audioTimestamp(clip.end_ms)}</button>
    </div>
    {failed ? <p role="status" className="text-sm">เสียงไม่พร้อมใช้งาน กรุณาค้นหาใหม่</p> : <audio ref={player} controls preload="metadata" aria-label={`เสียงอ้างอิง ${clip.title}`} className="h-10 w-full min-w-0" src={buildApiUrl(clip.audio_url)} onLoadedMetadata={() => { setReady(true); if (player.current) player.current.currentTime = clip.start_ms / 1000; }} onError={() => setFailed(true)} />}
    {clip.transcript ? <details className="text-sm"><summary className="cursor-pointer">บทถอดเสียง</summary><div className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words text-gray-600 dark:text-gray-300">{clip.transcript}</div></details> : <p className="text-xs text-gray-500">ไม่มีบทถอดเสียง</p>}
  </article>;
}

export function KnowledgeAudio({ audio }: { audio: KnowledgeAudioClip[] }) {
  if (!audio.length) return null;
  return <section aria-label="เสียงอ้างอิง" className="min-w-0 space-y-2"><div className="text-sm font-medium">เสียงอ้างอิง</div>{audio.map((clip) => <AudioClip key={`${clip.asset_id}-${clip.segment_id}`} clip={clip} />)}</section>;
}
