"use client";
import { useAdminLocale } from "@/lib/admin-locale";
import type { AdminCopy } from "@/lib/admin-copy";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Archive, CheckCircle2, Clipboard, FileText, Globe, Grid3X3, ImageIcon, Music2, Video, Loader2, Trash2, Upload, X } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { FILE_EXTENSIONS, fileIssue, fileMediaKind, formatDuration, formatFileSize, parseCapabilities, type CapabilitiesState, type FileMediaKind } from "@/lib/knowledge-import";

import { KnowledgeTableEditor } from "@/components/KnowledgeTableEditor";
import { emptyTable, tableDraftIssue, tablesToFiles, type TableDraft } from "@/lib/knowledge-tables";

function presentFileIssue(issue: string | null, copy: AdminCopy) {
  if (!issue) return null;
  if (issue === "Unsupported file type") return copy.fileUnsupported;
  if (issue === "Exceeds 10 MB limit") return copy.fileTooLarge(10);
  if (issue === "Exceeds 50 MB limit") return copy.fileTooLarge(50);
  if (issue === "Media readiness has not been confirmed") return copy.mediaNotConfirmed;
  if (issue === "Image import disabled") return copy.imageImportDisabled;
  if (issue === "Audio import disabled") return copy.audioImportDisabled;
  if (issue === "Video import disabled") return copy.videoImportDisabled;
  return issue;
}

function FilePreview({ file, disabled, issue, onRemove }: { file: File; disabled: boolean; issue: string | null; onRemove: () => void }) {
  const { copy } = useAdminLocale();
  const kind = fileMediaKind(file.name);
  const [url, setUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  useEffect(() => {
    if (kind !== "image" && kind !== "audio" && kind !== "video") return;
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file, kind]);
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
      <div className="flex items-start gap-3">
        {kind === "image" && url ? <img src={url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" /> : kind === "audio" ? <Music2 className="mt-1 h-5 w-5 shrink-0 text-gray-400" /> : <FileText className="mt-1 h-5 w-5 shrink-0 text-gray-400" />}
        <div className="min-w-0 flex-1">
          <div title={file.name} className="break-all text-sm font-medium text-gray-900 dark:text-white">{file.name}</div>
          <div className="mt-0.5 text-xs text-gray-500">{formatFileSize(file.size)}{duration !== null ? ` · ${formatDuration(duration)}` : ""}</div>
          {issue && <p className="mt-1 text-xs text-red-700 dark:text-red-300">{presentFileIssue(issue, copy)}</p>}
        </div>
        <button type="button" title={copy.removeNamed(file.name)} aria-label={copy.removeNamed(file.name)} onClick={onRemove} disabled={disabled} className="shrink-0 rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-50"><X className="h-4 w-4" /></button>
      </div>
      {kind === "video" && url && <video controls playsInline preload="metadata" src={url} className="mt-2 max-h-48 w-full rounded" aria-label={copy.previewNamed(file.name)} onLoadedMetadata={(event) => { const seconds = event.currentTarget.duration; if (Number.isFinite(seconds) && seconds > 0) setDuration(seconds * 1000); }} />}
      {kind === "audio" && url && <audio controls preload="metadata" src={url} className="mt-2 h-9 w-full min-w-0" aria-label={copy.previewNamed(file.name)} onLoadedMetadata={(event) => { const seconds = event.currentTarget.duration; if (Number.isFinite(seconds) && seconds > 0) setDuration(seconds * 1000); }} />}
    </div>
  );
}

interface CreateOKFBundleModalProps {
  teamAgentId?: number | null;
  assignAgentId?: number | null;
  teamSetupMode?: boolean;
  teamName?: string | null;
  onClose: () => void;
  onSuccess: (result: KnowledgeImportResult) => void;
  jobStorageKey?: string;
  onReturnToTeam?: () => void;
}

export type KnowledgeImportResult = { job_id: string; bundle_id: number; tool_id: number; display_name: string };

type ImportMode = "files" | "paste" | "urls" | "archive" | "table";

interface KnowledgePreview {
  source_count: number;
  concept_count: number;
  warnings: string[];
  tables?: Array<{
    table_name: string;
    source_file: string;
    sheet_name: string | null;
    columns: Array<{ name: string; type: string }>;
    row_count: number;
  }>;
  documents: Array<{
    title: string;
    source_file: string;
    document_type: string;
    character_count: number;
    excerpt: string;
    media_kind: "document" | "image" | "audio" | "video";
    duration_ms: number | null;
    text_status: "ready" | "not_requested" | "unavailable" | "empty";
    text: string;
    text_truncated: boolean;
  }>;
}

interface ImportJob {
  job_id: string;
  status: "queued" | "processing" | "succeeded" | "failed";
  message: string;
  bundle?: {
    id: number;
    display_name: string;
    concept_count: number;
    link_count: number;
    validation_summary?: { warnings?: string[] };
    tool_id?: number;
  } | null;
  error?: string | null;
  warnings: string[];
}

function parseImportJob(value: unknown): ImportJob {
  if (!value || typeof value !== "object" || !("job_id" in value) || typeof value.job_id !== "string" || !value.job_id || !("status" in value) || !["queued", "processing", "succeeded", "failed"].includes(String(value.status))) throw new Error("The server returned an invalid import job.");
  const status = value.status;
  if (status !== "queued" && status !== "processing" && status !== "succeeded" && status !== "failed") throw new Error("Invalid import status.");
  const job: ImportJob = { job_id: value.job_id, status, message: "message" in value && typeof value.message === "string" ? value.message : "", warnings: "warnings" in value && Array.isArray(value.warnings) ? value.warnings.filter((warning): warning is string => typeof warning === "string") : [] };
  if ("error" in value && typeof value.error === "string") job.error = value.error;
  if ("bundle" in value && value.bundle && typeof value.bundle === "object") {
    const bundle = value.bundle;
    if ("id" in bundle && typeof bundle.id === "number" && "tool_id" in bundle && typeof bundle.tool_id === "number" && "display_name" in bundle && typeof bundle.display_name === "string") {
      job.bundle = { id: bundle.id, tool_id: bundle.tool_id, display_name: bundle.display_name, concept_count: "concept_count" in bundle && typeof bundle.concept_count === "number" ? bundle.concept_count : 0, link_count: "link_count" in bundle && typeof bundle.link_count === "number" ? bundle.link_count : 0 };
    }
  }
  return job;
}

function completedImport(job: ImportJob): KnowledgeImportResult {
  const bundle = job.bundle;
  if (!bundle || !Number.isSafeInteger(bundle.id) || bundle.id <= 0 || typeof bundle.tool_id !== "number" || !Number.isSafeInteger(bundle.tool_id) || bundle.tool_id <= 0) throw new Error("The import completed without a valid knowledge tool. Reopen Add Knowledge to check again.");
  return { job_id: job.job_id, bundle_id: bundle.id, tool_id: bundle.tool_id, display_name: bundle.display_name };
}

const MODE_OPTIONS = [
  { id: "files", Icon: FileText },
  { id: "paste", Icon: Clipboard },
  { id: "urls", Icon: Globe },
  { id: "table", Icon: Grid3X3 },
] satisfies Array<{ id: ImportMode; Icon: typeof FileText }>;

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export default function CreateOKFBundleModal({
  teamAgentId,
  assignAgentId,
  teamSetupMode = false,
  teamName,
  onClose,
  onSuccess,
  onReturnToTeam,
  jobStorageKey,
}: CreateOKFBundleModalProps) {
  const { copy } = useAdminLocale();
  const headingId = useId();
  const pollController = useRef<AbortController | null>(null);
  const pendingImport = useRef<string | null>(null);
  const startController = useRef<AbortController | null>(null);
  const importInFlight = useRef(false);
  const deliveredJobs = useRef(new Set<string>());
  const onSuccessRef = useRef(onSuccess);
  useEffect(() => { onSuccessRef.current = onSuccess; }, [onSuccess]);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);
  useEffect(() => {
    const body = document.body;
    const previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    setPortalHost(body);
    return () => { body.style.overflow = previousOverflow; };
  }, []);
  const apiBaseUrl = getApiBaseUrl();
  const [displayName, setDisplayName] = useState("");
  const [visibility, setVisibility] = useState("team");
  const [mode, setMode] = useState<ImportMode>("files");
  const [knowledgeFiles, setKnowledgeFiles] = useState<File[]>([]);
  const [archiveFiles, setArchiveFiles] = useState<File[]>([]);
  const [tableDrafts, setTableDrafts] = useState<TableDraft[]>(() => [emptyTable()]);
  const [tableImporting, setTableImporting] = useState(false);
  const [tableDirty, setTableDirty] = useState(false);
  const [tableExpanded, setTableExpanded] = useState(false);
  const [queryable, setQueryable] = useState(false);
  const hasTableFiles = mode === "files" && knowledgeFiles.some((file) => /\.(csv|xlsx)$/i.test(file.name));
  useEffect(() => { if (!hasTableFiles) setQueryable(false); }, [hasTableFiles]);
  const files = mode === "archive" ? archiveFiles : knowledgeFiles;
  const setFiles = mode === "archive" ? setArchiveFiles : setKnowledgeFiles;
  const [capabilities, setCapabilities] = useState<CapabilitiesState>({ status: "loading" });
  const [readinessRevision, setReadinessRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setCapabilities({ status: "loading" });
    const token = localStorage.getItem("adminToken");
    const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
    fetch(`${apiBaseUrl}/api/admin/okf-bundles/import-capabilities${params}`, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error("Readiness unavailable"); return parseCapabilities(await response.json()); })
      .then((value) => { if (!controller.signal.aborted) setCapabilities({ status: "loaded", value }); })
      .catch(() => { if (!controller.signal.aborted) setCapabilities({ status: "unknown" }); });
    return () => controller.abort();
  }, [apiBaseUrl, teamAgentId, readinessRevision]);
  useEffect(() => { if (knowledgeFiles.some((file) => ["image", "audio", "video"].includes(fileMediaKind(file.name) || ""))) setPreview(null); }, [capabilities, knowledgeFiles]);
  const [pastedText, setPastedText] = useState("");
  const [urlText, setUrlText] = useState("");
  const urls = useMemo(() => urlText.split(/\r?\n/).map((url) => url.trim()).filter(Boolean), [urlText]);
  const [importing, setImporting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [draggingFiles, setDraggingFiles] = useState(false);
  const [preview, setPreview] = useState<KnowledgePreview | null>(null);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasSource = useMemo(() => {
    if (mode === "urls") return urls.length > 0;
    if (mode === "paste") return pastedText.trim().length > 0;
    if (mode === "table") return tableDrafts.some(table => table.rows.some(row => row.some(cell => cell.trim())));
    return files.length > 0;
  }, [files.length, mode, pastedText, urls.length, tableDrafts]);
  const importSucceeded = importJob?.status === "succeeded";
  const importFailed = importJob?.status === "failed";
  useEffect(() => {
    if (!tableDirty || importSucceeded || typeof window === "undefined") return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [tableDirty, importSucceeded]);

  const accept = mode === "archive" ? FILE_EXTENSIONS.archive : [FILE_EXTENSIONS.document, FILE_EXTENSIONS.archive,
    capabilities.status === "loaded" && capabilities.value.images.status === "ready" ? FILE_EXTENSIONS.image : "",
    capabilities.status === "loaded" && capabilities.value.audio.status === "ready" ? FILE_EXTENSIONS.audio : "",
    capabilities.status === "loaded" && capabilities.value.videos.status === "ready" ? FILE_EXTENSIONS.video : ""].filter(Boolean).join(",");
  const selectedBytes = files.reduce((total, file) => total + file.size, 0);
  const uploadIssue = mode === "files" && selectedBytes > MAX_UPLOAD_BYTES ? copy.uploadTooLarge : null;
  const selectedIssues = mode === "files" || mode === "archive" ? [...files.map((file) => fileIssue(file, capabilities, mode === "archive")).filter(Boolean), ...(uploadIssue ? [uploadIssue] : [])] : [];

  const resetSource = (nextMode: ImportMode) => {
    setMode(nextMode);
    setTableExpanded(false);
    setQueryable(false);
    setPreview(null);
    setImportJob(null);
    setError(null);
  };

  const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

  const addFiles = (nextFiles: FileList | File[] | null) => {
    if (importing || previewing) return;
    const incoming = Array.from(nextFiles || []);
    const rejected = incoming.filter((file) => fileIssue(file, capabilities, mode === "archive"));
    const selected = incoming.filter((file) => !fileIssue(file, capabilities, mode === "archive"));
    setError(rejected.length ? rejected.map((file) => `${file.name}: ${presentFileIssue(fileIssue(file, capabilities, mode === "archive"), copy)}`).join("; ") : null);
    if (selected.length === 0) return;
    setImportJob(null);
    setFiles((current) => {
      const existing = new Set(current.map(fileKey));
      const merged = [...current];
      for (const file of selected) {
        if (!existing.has(fileKey(file))) {
          merged.push(file);
          existing.add(fileKey(file));
        }
      }
      return mode === "archive" ? selected.slice(-1) : merged;
    });
    setPreview(null);
    if (!displayName.trim()) {
      const firstName = selected[0].name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
      setDisplayName(firstName);
    }
  };

  const removeFile = (target: File) => {
    setFiles((current) => current.filter((file) => fileKey(file) !== fileKey(target)));
    setPreview(null);
    setImportJob(null);
    setError(null);
  };

  const clearFiles = () => {
    setFiles([]);
    setPreview(null);
    setImportJob(null);
    setError(null);
  };

  const buildFormData = () => {
    const formData = new FormData();
    formData.append("display_name", displayName.trim());
    formData.append("visibility", visibility);
    formData.append("import_mode", mode === "archive" ? "archive" : mode === "urls" ? "urls" : "knowledge");
    formData.append("create_tool", "true");
    if ((hasTableFiles && queryable) || mode === "table") formData.append("queryable", "true");
    if (assignAgentId) formData.append("assign_agent_id", String(assignAgentId));
    if (mode === "table") {
      tablesToFiles(tableDrafts).forEach(file => formData.append("files", file));
    } else if (mode === "urls") {
      urls.forEach((url) => formData.append("urls", url));
    } else if (mode === "paste") {
      formData.append("pasted_text", pastedText.trim());
    } else {
      files.forEach((file) => formData.append("files", file));
    }
    return formData;
  };

  const handlePreview = async () => {
    if (tableImporting || !displayName.trim() || !hasSource || mode === "archive" || selectedIssues.length) return;

    try {
      if (mode === "table" && tableDraftIssue(tableDrafts)) throw new Error(copy.tableDataIssue);
      setPreviewing(true);
      setError(null);
      const token = localStorage.getItem("adminToken");
      const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/preview${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: buildFormData(),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to review knowledge");
      }

      setPreview(await response.json());
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Failed to review knowledge");
    } finally {
      setPreviewing(false);
    }
  };

  const handleImport = async () => {
    if (pendingImport.current && !importInFlight.current) {
      setError(null); setImporting(true);
      await pollImportJob(pendingImport.current);
      return;
    }
    if (tableImporting || importInFlight.current || !displayName.trim() || !hasSource || selectedIssues.length) return;
    importInFlight.current = true;
    const controller = new AbortController();
    startController.current = controller;

    try {
      if (mode === "table" && tableDraftIssue(tableDrafts)) throw new Error(copy.tableDataIssue);
      setImporting(true);
      setImportJob(null);
      setError(null);
      const token = localStorage.getItem("adminToken");
      const formData = buildFormData();

      const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/import-jobs${params}`, {
        signal: controller.signal,
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to add knowledge");
      }

      const job = parseImportJob(await response.json());
      if (controller.signal.aborted) return;
      pendingImport.current = job.job_id;
      if (jobStorageKey) { try { sessionStorage.setItem(jobStorageKey, job.job_id); } catch {} }
      setImportJob(job);
      await pollImportJob(job.job_id);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Failed to add knowledge");
        setImporting(false);
      }
    } finally {
      importInFlight.current = false;
    }
  };

  const pollImportJob = useCallback(async (jobId: string) => {
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    const token = localStorage.getItem("adminToken");
    try {
      for (;;) {
        const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/import-jobs/${encodeURIComponent(jobId)}`, {
          headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (!response.ok) throw new Error("Failed to read import job status. Reopen Add Knowledge to resume.");
        const job = parseImportJob(await response.json());
        if (controller.signal.aborted) return;
        if (job.job_id !== jobId) throw new Error("The server returned a different import job.");
        if (job.status === "succeeded") {
          const result = completedImport(job);
          setImportJob(job);
          setImporting(false);
          pendingImport.current = null;
          if (jobStorageKey) { try { sessionStorage.removeItem(jobStorageKey); } catch {} }
          if (!deliveredJobs.current.has(jobId)) {
            deliveredJobs.current.add(jobId);
            onSuccessRef.current(result);
          }
          return;
        }
        setImportJob(job);
        if (job.status === "failed") {
          setImporting(false);
          pendingImport.current = null;
          if (jobStorageKey) { try { sessionStorage.removeItem(jobStorageKey); } catch {} }
          setError(job.error || "Failed to add knowledge");
          return;
        }
        await new Promise<void>((resolve) => {
          const finish = () => { clearTimeout(timer); controller.signal.removeEventListener("abort", finish); resolve(); };
          const timer = setTimeout(finish, 900);
          controller.signal.addEventListener("abort", finish, { once: true });
        });
        if (controller.signal.aborted) return;
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setImporting(false);
        setError(error instanceof Error ? error.message : "Failed to read import job status");
      }
    }
  }, [apiBaseUrl, jobStorageKey]);

  useEffect(() => {
    let pendingJobId: string | null = null;
    try { pendingJobId = jobStorageKey ? sessionStorage.getItem(jobStorageKey) : null; } catch {}
    if (pendingJobId) { pendingImport.current = pendingJobId; setImporting(true); void pollImportJob(pendingJobId); }
    return () => { pollController.current?.abort(); startController.current?.abort(); };
  }, [jobStorageKey, pollImportJob]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (tableImporting || !displayName.trim() || !hasSource || selectedIssues.length) return;
    if (mode !== "archive" && !preview) {
      await handlePreview();
      return;
    }
    await handleImport();
  };

  const close = () => { if (!tableDirty || importSucceeded || window.confirm(copy.tableDiscard)) onClose(); };

  if (!portalHost) return null;

  return createPortal(
    <div className={`fixed inset-0 z-50 flex h-dvh w-screen items-center justify-center bg-black/50 ${tableExpanded ? "p-0" : "p-4"}`}>
      <div role="dialog" aria-modal={true} aria-busy={importing || previewing || tableImporting} aria-labelledby={headingId} onKeyDown={event => { if (event.key === "Escape" && tableExpanded) { event.preventDefault(); event.stopPropagation(); setTableExpanded(false); } }} className={`w-full overflow-hidden bg-white shadow-xl dark:bg-gray-800 ${tableExpanded ? "h-dvh max-h-dvh rounded-none" : `max-h-[92vh] rounded-lg ${mode === "table" ? "max-w-6xl" : "max-w-3xl"}`}`}>
        <div className="flex items-center justify-between border-b border-gray-200 p-4 sm:p-6 dark:border-gray-700">
          <div>
            <h2 id={headingId} className="text-xl font-semibold text-gray-900 dark:text-white">
              {copy.addKnowledge}
            </h2>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label={copy.closeAddKnowledge}
            disabled={importing || previewing || tableImporting}
            className="text-gray-400 hover:text-gray-500 disabled:opacity-50 dark:hover:text-gray-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className={`${tableExpanded ? "max-h-[calc(100dvh-90px)]" : "max-h-[calc(92vh-90px)]"} overflow-y-auto p-4 sm:p-6`}>
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-900" role="group" aria-label={copy.knowledgeSource}>
            {MODE_OPTIONS.map(({ id, Icon }) => <button key={id} type="button" aria-pressed={mode === id} data-admin-write="true" onClick={() => resetSource(id)} disabled={importing || previewing || tableImporting} className={`flex min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-md sm:flex-row sm:gap-2 px-2 py-2 text-sm font-medium ${mode === id ? "bg-white text-emerald-800 shadow-sm dark:bg-gray-700 dark:text-emerald-200" : "text-gray-600 dark:text-gray-300"}`}><Icon className="h-4 w-4" />{id === "files" ? copy.files : id === "paste" ? copy.pasteText : id === "table" ? copy.tables : copy.websites}</button>)}
          </div>
          <details className="mt-3 text-xs text-gray-500" open={mode === "archive" ? true : undefined}>
            <summary className="cursor-pointer">{copy.advanced}</summary>
            <button type="button" data-admin-write="true" onClick={() => resetSource("archive")} disabled={importing || previewing || tableImporting} className={`mt-2 inline-flex items-center gap-2 rounded border px-3 py-2 ${mode === "archive" ? "border-emerald-500 text-emerald-700" : "border-gray-200"}`}><Archive className="h-4 w-4" />{copy.preparedArchive}</button>
          </details>

          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="knowledge-name" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                {copy.knowledgeName}
              </label>
              <input
                id="knowledge-name"
                type="text"
                value={displayName}
                data-admin-write="true" onChange={(event) => {
                  setDisplayName(event.target.value);
                  setPreview(null);
                }}
                disabled={importing || previewing || tableImporting}
                placeholder=""
                className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                required
              />
            </div>

            {teamAgentId && (
              <div>
                <label htmlFor="knowledge-visibility" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {copy.visibility}
                </label>
                <select
                  id="knowledge-visibility"
                value={visibility}
                  data-admin-write="true" onChange={(event) => {
                    setVisibility(event.target.value);
                    setPreview(null);
                  }}
                  disabled={importing || previewing || tableImporting}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="team">{copy.privateTeam}</option>
                  <option value="global">{copy.sharedAllTeams}</option>
                </select>
              </div>
            )}

            {mode === "table" ? <KnowledgeTableEditor expanded={tableExpanded} onToggleExpanded={() => setTableExpanded(value => !value)} tables={tableDrafts} onChange={next => { setTableDrafts(next); setTableDirty(true); setPreview(null); setImportJob(null); setError(null); }} teamAgentId={teamAgentId} onBusyChange={setTableImporting} disabled={importing || previewing} /> : mode === "urls" ? (
              <div>
                <label htmlFor="knowledge-urls" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {copy.sourceUrls}
                </label>
                <textarea
                  id="knowledge-urls"
                  value={urlText}
                  data-admin-write="true" onChange={(event) => {
                    setUrlText(event.target.value);
                    setPreview(null);
                    setImportJob(null);
                    setError(null);
                  }}
                  disabled={importing || previewing || tableImporting}
                  rows={6}
                  placeholder={"https://example.com/policy\nhttps://example.com/faq"}
                  aria-describedby="knowledge-urls-hint"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
                <p id="knowledge-urls-hint" className="mt-1 text-xs text-gray-500">{copy.urlsHint}</p>
              </div>
            ) : mode === "paste" ? (
              <div>
                <label htmlFor="knowledge-text" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {copy.knowledgeText}
                </label>
                <textarea
                  id="knowledge-text"
                  value={pastedText}
                  data-admin-write="true" onChange={(event) => {
                    setPastedText(event.target.value);
                    setPreview(null);
                    setError(null);
                  }}
                  disabled={importing || previewing || tableImporting}
                  rows={10}
                  placeholder={copy.knowledgePlaceholder}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
            ) : (
              <div>
                {mode === "files" && <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {(["document", "image", "audio", "video"] satisfies FileMediaKind[]).map((kind) => {
                    const capability = kind === "document" ? { status: "ready" } : capabilities.status === "loaded" ? (kind === "image" ? capabilities.value.images : kind === "video" ? capabilities.value.videos : capabilities.value.audio) : null;
                    const ready = capability?.status === "ready";
                    const Icon = kind === "image" ? ImageIcon : kind === "audio" ? Music2 : kind === "video" ? Video : FileText;
                    const label = kind === "image" ? copy.images : kind === "audio" ? copy.audio : kind === "video" ? copy.videos : copy.documents;
                    const status = ready ? copy.ready : capability?.status === "disabled" ? copy.disabled : capabilities.status === "loading" ? copy.checking : copy.unavailable;
                    return <label key={kind} className={`rounded-md border border-gray-200 p-3 dark:border-gray-600 ${ready && !importing && !previewing ? "cursor-pointer hover:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-2" : "opacity-60"}`}>
                      <span className="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-100"><Icon className="h-4 w-4" />{label}</span>
                      <span className="mt-1 block text-xs text-gray-500">{kind === "image" ? "JPG, PNG · 10 MB" : kind === "audio" ? "WAV, MP3 · 50 MB · 10 min" : kind === "video" ? "MP4, MOV, WebM · 50 MB" : "PDF, Office, text, archives · 50 MB"}</span>
                      <span className={`mt-1 block text-xs ${ready ? "text-emerald-700 dark:text-emerald-300" : "text-gray-500"}`}>{status}</span>
                      <input type="file" data-admin-write="true" aria-label={copy.addNamed(label)} accept={kind === "document" ? `${FILE_EXTENSIONS.document},${FILE_EXTENSIONS.archive}` : FILE_EXTENSIONS[kind]} multiple disabled={!ready || importing || previewing} className="sr-only" onChange={(event) => { addFiles(event.target.files); event.currentTarget.value = ""; }} />
                    </label>;
                  })}
                </div>}
                {mode === "files" && <div className="mb-3 text-xs text-gray-500" aria-live="polite">
                  {capabilities.status === "unknown" ? copy.mediaReadinessUnknown : capabilities.status === "loaded" && [capabilities.value.images, capabilities.value.audio, capabilities.value.videos].some((item) => item.status === "unavailable") ? <>{copy.mediaUnavailable}<details className="mt-1"><summary>{copy.errorDetails}</summary>{[capabilities.value.images, capabilities.value.audio, capabilities.value.videos].filter((item) => item.status === "unavailable").map((item) => item.status === "unavailable" ? item.reason : "").join(" · ")}</details></> : ""}
                  {(capabilities.status === "unknown" || (capabilities.status === "loaded" && [capabilities.value.images, capabilities.value.audio, capabilities.value.videos].some((item) => item.status === "unavailable" && item.retryable))) && <button type="button" className="ml-2 text-emerald-700 underline" onClick={() => { setError(null); setReadinessRevision((value) => value + 1); }} disabled={importing || previewing || tableImporting}>{copy.retry}</button>}
                  {capabilities.status === "loaded" && capabilities.value.images.status === "ready" && <span className="block mt-1">{capabilities.value.image_ocr.status === "configured" ? copy.ocrConfigured : copy.ocrUnavailable}</span>}
                </div>}
                <label className={`flex items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 text-sm text-gray-600 dark:text-gray-300 ${importing || previewing ? "opacity-60" : "cursor-pointer focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-2"} ${draggingFiles ? "border-emerald-500 bg-emerald-50" : "border-gray-300 dark:border-gray-600"}`}
                  onDragOver={(event) => { event.preventDefault(); if (!importing && !previewing) setDraggingFiles(true); }} onDragLeave={() => setDraggingFiles(false)} onDrop={(event) => { event.preventDefault(); setDraggingFiles(false); addFiles(event.dataTransfer.files); }}>
                  <input type="file" data-admin-write="true" aria-label={mode === "archive" ? copy.addArchive : copy.addFiles} accept={accept} multiple={mode !== "archive"} className="sr-only" disabled={importing || previewing || tableImporting} onChange={(event) => { addFiles(event.target.files); event.currentTarget.value = ""; }} />
                  <Upload className="h-5 w-5 shrink-0" />{mode === "archive" ? copy.chooseArchive : copy.dropFiles}
                </label>
                {mode === "files" && <p className="mt-1 text-xs text-gray-500">{copy.uploadTotal}</p>}
                {files.length > 0 && <div className="mt-3">
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs text-gray-500"><span>{copy.filesSelected(files.length, formatFileSize(selectedBytes))}</span><button type="button" onClick={clearFiles} disabled={importing || previewing || tableImporting} className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-100"><Trash2 className="h-3.5 w-3.5" />{copy.clearAll}</button></div>
                  {uploadIssue && <p role="alert" className="mb-2 text-sm text-red-700 dark:text-red-300">{uploadIssue}</p>}
                  <div className="max-h-72 space-y-2 overflow-y-auto">{files.map((file) => <FilePreview key={fileKey(file)} file={file} issue={fileIssue(file, capabilities, mode === "archive")} disabled={importing || previewing || tableImporting} onRemove={() => removeFile(file)} />)}</div>
                </div>}
                {hasTableFiles && <div className="mt-3 rounded-md border border-gray-200 p-3 dark:border-gray-700">
                  <label className="flex items-start gap-2 text-sm font-medium text-gray-800 dark:text-gray-100">
                    <input type="checkbox" checked={queryable} data-admin-write="true" aria-describedby={`${headingId}-queryable-hint`} disabled={importing || previewing || tableImporting} onChange={(event) => { setQueryable(event.target.checked); setPreview(null); setImportJob(null); setError(null); }} className="mt-0.5 h-4 w-4 shrink-0 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500" />
                    {copy.queryableTablesOption}
                  </label>
                  <div id={`${headingId}-queryable-hint`} className="mt-1 pl-6 text-xs text-gray-500">{copy.queryableTablesHint}</div>
                </div>}
              </div>
            )}

            {preview && mode !== "archive" && (
              <div className="rounded-lg border border-emerald-200 bg-white p-4 dark:border-emerald-900/50 dark:bg-gray-900">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                      {copy.sourceReady}
                    </h3>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                      {copy.sourcesAndConcepts(preview.source_count, preview.concept_count)}
                    </p>
                  </div>
                </div>
                {preview.warnings.length > 0 && (
                  <details className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-100">
                    <summary className="cursor-pointer font-semibold">{copy.reviewNotes(preview.warnings.length)}</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {preview.warnings.map((warning, index) => (
                        <li key={`${warning}-${index}`}>{warning}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {preview.tables && preview.tables.length > 0 && <details className="mt-4 rounded-md border border-gray-200 p-3 text-sm dark:border-gray-700">
                  <summary className="cursor-pointer font-medium text-gray-800 dark:text-gray-100">{copy.queryableTablesCount(preview.tables.length)}</summary>
                  <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto text-xs text-gray-600 dark:text-gray-300">
                    {preview.tables.map((table) => <li key={table.table_name} className="break-words">
                      <span className="font-medium">{table.source_file}{table.sheet_name ? ` · ${table.sheet_name}` : ""}</span>
                      <span className="mt-0.5 block">{copy.tableDimensions(table.row_count, table.columns.length)}</span>
                    </li>)}
                  </ul>
                </details>}
                <div className="mt-4 space-y-2">
                  {preview.documents.map((document) => (
                    <div key={`${document.source_file}-${document.character_count}`} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div title={document.title} className="break-words text-sm font-medium text-gray-900 dark:text-white">{document.title}</div>
                          <div title={document.source_file} className="mt-0.5 break-all text-xs text-gray-500 dark:text-gray-400">{document.source_file}</div>
                        </div>
                        <span className="shrink-0 rounded-full bg-gray-100 px-2 py-1 text-[11px] font-medium uppercase text-gray-600 dark:bg-gray-700 dark:text-gray-200">
                          {document.document_type}
                        </span>
                      </div>
                      {document.duration_ms != null && <p className="mt-1 text-xs text-gray-500">{formatDuration(document.duration_ms)}</p>}
                      {document.text_status === "ready" && document.text && <details className="mt-2 text-xs text-gray-600 dark:text-gray-300"><summary className="cursor-pointer font-medium">{document.media_kind === "image" ? copy.extractedImageText : copy.extractedText} · {copy.characters(document.character_count)}</summary><pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-3 font-sans text-sm leading-6 dark:bg-gray-800">{document.text}</pre>{document.text_truncated && <p className="mt-1 text-gray-500">{copy.previewLimit}</p>}</details>}
                      {document.text_status !== "ready" && <p className="mt-2 text-xs text-gray-500">{document.media_kind === "video" && document.text_status === "not_requested" ? copy.videoDuringImport : document.media_kind === "audio" && document.text_status === "not_requested" ? copy.transcriptDuringImport : document.text_status === "unavailable" ? copy.textUnavailable : document.text_status === "not_requested" ? copy.ocrNotRequested : copy.noReadableText}</p>}

                    </div>
                  ))}
                </div>
              </div>
            )}

            {importJob && (
              <div
                className={[
                  "rounded-lg border p-4",
                  importSucceeded
                    ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900/50 dark:bg-emerald-900/20"
                    : importFailed
                      ? "border-red-200 bg-red-50 dark:border-red-900/50 dark:bg-red-900/20"
                      : "border-blue-200 bg-blue-50 dark:border-blue-900/50 dark:bg-blue-900/20",
                ].join(" ")}
              >
                <div className="flex items-start gap-3">
                  {importSucceeded ? (
                    <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                  ) : importFailed ? (
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
                  ) : (
                    <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-blue-600" />
                  )}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                      {importSucceeded ? copy.localKnowledgeReady : importFailed ? copy.importFailed : copy.creatingKnowledge}
                    </h3>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                      {importJob.message}
                    </p>
                    {importJob.bundle && (
                      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                        {copy.indexedConcepts(importJob.bundle.concept_count)}
                        {importJob.bundle.tool_id ? ` · ${copy.capabilityCreated}` : "."}
                      </p>
                    )}
                    {importSucceeded && teamSetupMode && (
                      <div className="mt-3 rounded-md border border-emerald-200 bg-white/70 p-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-gray-900/40 dark:text-emerald-100">
                        {assignAgentId
                          ? copy.assignedKnowledge
                          : copy.knowledgeReadyForTeam}
                      </div>
                    )}
                    {(importJob.warnings || []).length > 0 && (
                      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-900 dark:text-amber-100">
                        {importJob.warnings.slice(0, 5).map((warning, index) => (
                          <li key={`${warning}-${index}`}>{warning}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            )}


            {error && (
              <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
                {copy.knowledgeIssue}<details className="mt-1"><summary>{copy.errorDetails}</summary>{error}</details>
                {pendingImport.current && !importing && <button type="button" data-admin-write="true" onClick={() => { void handleImport(); }} className="ml-3 font-medium underline">{copy.retryStatus}</button>}
              </div>
            )}
          </div>

          <div className="sticky bottom-0 mt-6 flex flex-wrap items-center justify-end gap-3 bg-white dark:bg-gray-800 border-t border-gray-200 pt-4 dark:border-gray-700">
            <button
              type="button"
              onClick={close}
              disabled={importing || previewing || tableImporting}
              className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              {copy.cancel}
            </button>
            {importSucceeded ? (
              <>
                {teamSetupMode && onReturnToTeam && (
                  <button
                    type="button"
                    onClick={onReturnToTeam}
                    className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                  >
                    {copy.backToTeam}
                  </button>
                )}
                <button
                  type="button"
                  onClick={close}
                  className={[
                    "rounded-md px-4 py-2 text-sm font-medium",
                    teamSetupMode && onReturnToTeam
                      ? "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                      : "bg-emerald-600 text-white hover:bg-emerald-700",
                  ].join(" ")}
                >
                  {copy.done}
                </button>
              </>
            ) : (
              <button
                type="submit" data-admin-write="true"
                disabled={importing || previewing || tableImporting || !displayName.trim() || !hasSource || selectedIssues.length > 0}
                className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {(importing || previewing) && <Loader2 className="h-4 w-4 animate-spin" />}
                {mode === "archive" ? copy.importOKF : preview ? copy.addKnowledge : copy.reviewKnowledge}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>,
    portalHost
  );
}
