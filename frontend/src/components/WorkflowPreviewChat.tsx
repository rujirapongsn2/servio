"use client";
import { useAdminLocale } from "@/lib/admin-locale";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { KnowledgeVideos } from "@/components/KnowledgeVideos";
import { KnowledgeAudio } from "@/components/KnowledgeAudio";
import { KnowledgeImages } from "@/components/KnowledgeImages";
import { ProductCarousel } from "@/components/ProductCarousel";
import { AnswerSurface } from "@/components/AnswerSurface";
import { ProductDiscovery } from "@/components/ProductDiscovery";
import { discoveryActionEnvelope, type DiscoveryAction } from "@/lib/a2ui-discovery";
import { buildApiUrl } from "@/lib/api";
import { normalizeMarkdownForChat } from "@/lib/markdown";
import { workflowRequest, type TeamWorkflow, type WorkflowAgentDraft } from "@/lib/team-workflow";
import { createPreviewConversation, parsePreviewReply, parsePreviewSession, previewDrafts, previewError, previewProductInquiry, previewSignature, previewTargetKey, readPreviewAttachment, type PreviewConversation, type PreviewReply } from "@/lib/workflow-preview";

type Props = {
  teamId: number;
  workflow: TeamWorkflow;
  drafts: Record<number, WorkflowAgentDraft>;
  targetAgentId: number | null;
  onTargetChange: (id: number | null) => void;
  onEditAgent: (id: number) => void;
  onOpenKnowledge: () => void;
  visible: boolean;
};

function ReplyContent({ reply, disabled, onInquiry, onAction }: { reply: PreviewReply; disabled: boolean; onInquiry: (message: string) => void; onAction: (id: string, action: DiscoveryAction) => boolean }) {
  const { locale } = useAdminLocale();
  const images = Object.values(reply.presentations).flatMap(presentation =>
    presentation.type === "knowledge_images" || presentation.type === "knowledge_media" ? presentation.images : []);
  const uniqueImages = [...new Map(images.map(image => [image.asset_id, image])).values()];
  const surfaces = Object.values(reply.surfaces);
  return <div className="min-w-0 space-y-3">
    {!surfaces.some(surface => surface.kind === "answer") && <div className="markdown-content min-w-0 break-words text-sm [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_table]:block [&_table]:overflow-x-auto">
      <ReactMarkdown remarkPlugins={[remarkGfm]} disallowedElements={["img"]}>{normalizeMarkdownForChat(reply.response)}</ReactMarkdown>
    </div>}
    {surfaces.map(surface => surface.kind === "answer" ? <AnswerSurface key={surface.id} surface={surface} locale={locale} />
      : <ProductDiscovery key={surface.id} surface={surface} disabled={disabled} onAction={onAction} />)}
    {reply.audioUrl && <audio controls src={buildApiUrl(reply.audioUrl)} aria-label={locale === "th" ? "เสียงคำตอบ" : "Spoken response"} />}
    {reply.mediaError && <p role="status" className="text-xs text-amber-700">{reply.mediaError}</p>}
    <KnowledgeImages images={uniqueImages} />
    {Object.entries(reply.presentations).map(([callId, presentation]) => {
      if (reply.surfaces[callId]?.kind === "discovery") return null;
      if (presentation.type === "knowledge_video") return <KnowledgeVideos key={callId} videos={presentation.videos} locale={locale} />;
      if (presentation.type === "knowledge_media") return <KnowledgeAudio key={callId} audio={presentation.audio} />;
      if (presentation.type === "knowledge_images") return null;
      return <ProductCarousel key={callId} presentation={presentation} disabled={disabled} onInquire={productId => {
        const message = previewProductInquiry(reply.presentations, callId, productId);
        if (message) onInquiry(message);
      }} />;
    })}
  </div>;
}

export default function WorkflowPreviewChat({ teamId, workflow, drafts, targetAgentId, onTargetChange, onEditAgent, onOpenKnowledge, visible }: Props) {
  const { copy, locale } = useAdminLocale();
  const th = locale === "th";
  const fileInput = useRef<HTMLInputElement>(null);
  const conversations = useRef(new Map<string, PreviewConversation>());
  const [, rerender] = useState(0);
  const end = useRef<HTMLDivElement>(null);
  const lifetime = useRef(0);
  const key = previewTargetKey(teamId, targetAgentId);
  let conversation = conversations.current.get(key);
  if (!conversation) {
    conversation = createPreviewConversation();
    conversations.current.set(key, conversation);
  }
  const current = conversation;
  const signature = previewSignature(workflow, drafts);
  const changed = current.signature !== null && current.signature !== signature;
  const target = workflow.agents.find(agent => agent.id === targetAgentId);
  const targetRemoved = targetAgentId !== null && !target;
  const busy = current.phase === "busy";
  const pending = current.phase === "pending";
  const blocked = busy || pending;
  const expired = current.phase === "expired" || current.session !== null && current.session.expiresAt <= Date.now();
  const lastReply = current.messages.findLast(message => message.kind === "assistant");
  const activeAgent = target || (lastReply?.kind === "assistant" ? workflow.agents.find(agent => (drafts[agent.id]?.name || agent.name) === lastReply.reply.agentName) : undefined);
  const refresh = () => rerender(value => value + 1);
  const base = `/team-agents/${teamId}/workflow/previews`;
  const removeSession = (id: string) => workflowRequest(`${base}/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(() => undefined);

  useEffect(() => {
    const generation = ++lifetime.current;
    const entries = conversations.current;
    function dispose(entryKey: string, entry: PreviewConversation) {
      entries.delete(entryKey);
      if (entry.session) void workflowRequest(`/team-agents/${entryKey.split(":")[0]}/workflow/previews/${encodeURIComponent(entry.session.id)}`, { method: "DELETE" }).catch(() => undefined);
    }
    for (const [entryKey, entry] of entries) {
      if (!entryKey.startsWith(`${teamId}:`)) dispose(entryKey, entry);
    }
    return () => {
      queueMicrotask(() => {
        if (generation !== lifetime.current) return;
        for (const [entryKey, entry] of entries) dispose(entryKey, entry);
      });
    };
  }, [teamId]);
  useEffect(() => {
    if (visible) end.current?.scrollIntoView({ block: "end" });
  }, [visible, key, current.messages.length, busy]);

  async function send(message = current.composer) {
    const content = message.trim();
    if ((!content && !current.attachments.length) || current.phase === "busy" || current.phase === "pending" || expired || targetRemoved) return;
    if (!current.session && !window.confirm(copy.confirmRealTools)) return;
    current.phase = "busy";
    current.error = null;
    const requestSignature = signature;
    const requestDrafts = previewDrafts(workflow, drafts);
    refresh();
    const isCurrent = () => conversations.current.get(key) === current;
    try {
      if (!current.session) {
        const session = parsePreviewSession(await workflowRequest(base, { method: "POST", body: JSON.stringify({ target_agent_id: targetAgentId, drafts: requestDrafts, confirm_real_tools: true }) }));
        if (!isCurrent()) { void removeSession(session.id); return; }
        current.session = session;
        current.signature = requestSignature;
      }
      if (!isCurrent()) return;
      const attachments = current.attachments;
      current.messages.push({ kind: "user", content, attachments });
      current.attachments = [];
      if (current.composer.trim() === content) current.composer = "";
      refresh();
      const requestId = crypto.randomUUID();
      current.pendingRequestId = requestId;
      const reply = parsePreviewReply(await workflowRequest(`${base}/${encodeURIComponent(current.session.id)}/messages`, { method: "POST", body: JSON.stringify({ message: content, attachments, speak: current.speak,
        image_search: current.imageSearch && attachments.length === 1 && attachments[0].kind === "image", request_id: requestId }) }));
      if (!isCurrent()) return;
      current.messages.push({ kind: "assistant", reply });
      current.phase = "idle";
      current.pendingRequestId = null;
      current.session.expiresAt = Date.now() + 7200 * 1000;
    } catch (error) {
      if (!isCurrent()) return;
      const failure = previewError(error);
      current.error = failure.message;
      current.phase = failure.expired ? "expired" : current.pendingRequestId ? "pending" : "idle";
    } finally {
      if (isCurrent()) refresh();
    }
  }

  async function attach(files: FileList | null) {
    if (!files || blocked) return;
    try {
      const additions = await Promise.all(Array.from(files).map(readPreviewAttachment));
      const attachments = [...current.attachments, ...additions];
      if (attachments.length > 8 || attachments.reduce((sum, file) => sum + file.base64.length, 0) > 70 * 1024 * 1024) throw new Error(th ? "แนบไฟล์รวมไม่เกิน 50 MB" : "Attachments must total at most 50 MB");
      current.attachments = attachments;
    } catch (error) { current.error = error instanceof Error ? error.message : "Could not attach file"; }
    if (fileInput.current) fileInput.current.value = "";
    refresh();
  }

  async function checkResult() {
    if (!current.session) return;
    try {
      const status = await workflowRequest(`${base}/${encodeURIComponent(current.session.id)}`);
      if (typeof status !== "object" || status === null || !("busy" in status) || !("reply" in status)) throw new Error("Invalid status");
      if (status.busy) { current.error = th ? "ยังประมวลผลอยู่ กรุณารอ" : "Still processing; please wait"; }
      else {
        const reply = status.reply ? parsePreviewReply(status.reply) : null;
        if (reply && reply.requestId === current.pendingRequestId) current.messages.push({ kind: "assistant", reply });
        current.phase = "idle"; current.pendingRequestId = null; current.error = null;
      }
    } catch (error) { current.error = previewError(error).message; }
    refresh();
  }

  function action(surfaceId: string, request: DiscoveryAction): boolean {
    if (!current.session || current.phase === "busy" || current.phase === "pending" || expired) return false;
    const sessionId = current.session.id;
    const isCurrent = () => conversations.current.get(key) === current && current.session?.id === sessionId;
    current.phase = "busy"; refresh();
    void workflowRequest(`${base}/${encodeURIComponent(sessionId)}/actions`, { method: "POST", body: JSON.stringify(discoveryActionEnvelope(surfaceId, request)) }).then(value => {
      if (!isCurrent()) return;
      const reply = parsePreviewReply(value);
      if (request.name === "discovery.refine") {
        for (const message of current.messages) if (message.kind === "assistant") {
          for (const [id, surface] of Object.entries(reply.surfaces)) if (message.reply.surfaces[id]) message.reply.surfaces[id] = surface;
        }
      } else current.messages.push({ kind: "assistant", reply });
      current.phase = "idle";
    }).catch(error => { if (isCurrent()) { current.error = previewError(error).message; current.phase = "idle"; } }).finally(() => { if (isCurrent()) refresh(); });
    return true;
  }

  function restart() {
    if (!window.confirm(copy.confirmRestart)) return;
    const previous = current.session;
    const replacement = createPreviewConversation();
    replacement.composer = current.composer;
    conversations.current.set(key, replacement);
    refresh();
    if (previous) void removeSession(previous.id);
  }

  return <section hidden={!visible} aria-label={copy.preview} className={visible ? "flex h-[calc(100dvh-240px)] min-h-[420px] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" : "hidden"}>
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-gray-700">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <label htmlFor={`preview-target-${teamId}`} className="text-sm font-medium">{copy.chatWith}</label>
        <select id={`preview-target-${teamId}`} value={targetAgentId ?? "team"} onChange={event => onTargetChange(event.target.value === "team" ? null : Number(event.target.value))} className="max-w-full rounded-lg border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900">
          <option value="team">{copy.teamRouter}</option>
          {workflow.agents.map(agent => <option key={agent.id} value={agent.id}>{drafts[agent.id]?.name || agent.name}</option>)}
        </select>
        <span className="rounded-full bg-violet-50 px-2 py-1 text-xs text-violet-700 dark:bg-violet-950 dark:text-violet-200">{copy.privateChat}</span>
        {(current.session?.hasDrafts || !current.session && previewDrafts(workflow, drafts).length > 0) && <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">{copy.draftSettings}</span>}
        {!(current.session?.hasDrafts || !current.session && previewDrafts(workflow, drafts).length > 0) && <span className="rounded-full bg-slate-50 px-2 py-1 text-xs text-slate-600">{copy.savedSettings}</span>}
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        <button type="button" onClick={onOpenKnowledge} className="rounded-lg border px-3 py-2">{copy.knowledge}</button>
        {activeAgent && workflow.can_edit && !activeAgent.shared && <button type="button" onClick={() => onEditAgent(activeAgent.id)} className="rounded-lg border px-3 py-2">{copy.editAgent}</button>}
        <button type="button" disabled={!current.session && !busy && !current.messages.length} onClick={restart} className="rounded-lg border px-3 py-2 disabled:opacity-40">{copy.restart}</button>
      </div>
    </header>
    <div className="border-b border-gray-200 px-4 py-2 text-xs text-gray-500 dark:border-gray-700">
      {targetAgentId === null ? copy.teamRouting : copy.directConversation} · {copy.previewSessionNote}
      {current.session && current.session.blockedTools.length > 0 && <details className="mt-1"><summary className="cursor-pointer">{copy.toolsUnavailable(current.session.blockedTools.length)}</summary><p className="mt-1 break-words">{current.session.blockedTools.join(", ")}</p></details>}
    </div>
    {changed && <div role="status" className="bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">{copy.settingsChanged}</div>}
    {targetRemoved && <div role="alert" className="px-4 py-2 text-sm text-red-600">{copy.targetRemoved}</div>}
    <div role="log" aria-label={copy.previewConversation} aria-live="polite" aria-busy={busy} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
      <div className="mx-auto w-full max-w-4xl space-y-6">
        {current.messages.length === 0 && <p className="py-12 text-center text-sm text-gray-500">{copy.sendToTest(target ? drafts[target.id]?.name || target.name : copy.teamRouting)}</p>}
        {current.messages.map((message, index) => <article key={index} className={message.kind === "user" ? "ml-auto max-w-[90%] rounded-xl bg-gray-100 px-4 py-3 dark:bg-gray-800" : "min-w-0"}>
          <div className="mb-2 text-xs font-semibold text-gray-500">{message.kind === "user" ? copy.you : message.reply.agentName}</div>
          {message.kind === "user" ? <div><p className="whitespace-pre-wrap break-words text-sm">{message.content}</p>{message.attachments?.map((file, i) => <span key={i} className="mt-1 block text-xs text-gray-500">{file.name}</span>)}</div> : <>
            <ReplyContent reply={message.reply} disabled={blocked || expired || targetRemoved} onInquiry={content => void send(content)} onAction={action} />
            {message.reply.citations.length > 0 && <button type="button" className="mt-3 text-xs text-blue-600 underline" onClick={onOpenKnowledge}>{copy.knowledgeSourcesCount(message.reply.citations.length)}</button>}
            {message.reply.toolCalls.length > 0 && <details className="mt-3 text-xs text-gray-500"><summary className="cursor-pointer">{copy.toolActivityCount(message.reply.toolCalls.length)}</summary><pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(message.reply.toolCalls, null, 2)}</pre></details>}
          </>}
        </article>)}
        {busy && <p role="status" className="text-sm text-gray-500">{copy.thinking}</p>}
        <div ref={end} />
      </div>
    </div>
    <form onSubmit={event => { event.preventDefault(); void send(); }} className="border-t border-gray-200 p-4 dark:border-gray-700">
      <div className="mx-auto max-w-4xl">
        {current.error && <div role="alert" className="mb-2 break-words text-sm text-red-600">{copy.previewIssue}<details><summary>{copy.errorDetails}</summary>{current.error}</details></div>}
        {pending && <button type="button" onClick={() => void checkResult()} className="mb-2 rounded border px-3 py-2 text-sm">{th ? "ตรวจผลการทำงาน" : "Check result"}</button>}
        {expired && <p role="status" className="mb-2 text-sm text-amber-700">{copy.previewExpired}</p>}
        <label htmlFor={`preview-message-${teamId}`} className="mb-1 block text-xs font-medium text-gray-500">{copy.message}</label>
        <div className="flex items-end gap-2">
          <input ref={fileInput} type="file" multiple className="sr-only" aria-label={th ? "แนบรูปภาพ เสียง ไฟล์ หรือวิดีโอ" : "Attach image, audio, file or video"}
            accept="image/jpeg,image/png,audio/*,video/mp4,video/quicktime,video/webm,.pdf,.txt,.csv,.json,.md" onChange={event => void attach(event.target.files)} />
          <button type="button" disabled={blocked || expired} onClick={() => fileInput.current?.click()} className="rounded-lg border px-3 py-2 text-sm">{th ? "แนบไฟล์" : "Attach"}</button>
          <textarea id={`preview-message-${teamId}`} rows={2} value={current.composer} onChange={event => { current.composer = event.target.value; refresh(); }} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} className="min-w-0 flex-1 resize-y rounded-lg border bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900" />
          <button type="submit" disabled={blocked || expired || targetRemoved || (!current.composer.trim() && !current.attachments.length)} className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-40">{copy.send}</button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-500">
          <label className="flex items-center gap-1"><input type="checkbox" checked={current.speak} onChange={event => { current.speak = event.target.checked; refresh(); }} />{th ? "อ่านคำตอบ" : "Spoken reply"}</label>
          {current.attachments.some(file => file.kind === "image") && <label className="flex items-center gap-1"><input type="checkbox" checked={current.imageSearch} onChange={event => { current.imageSearch = event.target.checked; refresh(); }} />{th ? "ค้นหาสินค้าจากภาพ" : "Search catalog image"}</label>}
          {current.attachments.map((file, i) => <button key={i} type="button" onClick={() => { current.attachments.splice(i, 1); refresh(); }} className="max-w-56 truncate rounded border px-2 py-1" aria-label={`${th ? "นำออก" : "Remove"} ${file.name}`}>{file.name} ×</button>)}
        </div>
      </div>
    </form>
  </section>;
}
