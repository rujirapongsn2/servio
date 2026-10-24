"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, Archive, CheckCircle2, Clipboard, FileText, Globe, ImageIcon, Music2, Loader2, Trash2, Upload, X } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { FILE_EXTENSIONS, fileIssue, fileMediaKind, formatDuration, formatFileSize, parseCapabilities, type CapabilitiesState, type FileMediaKind } from "@/lib/knowledge-import";

function FilePreview({ file, disabled, issue, onRemove }: { file: File; disabled: boolean; issue: string | null; onRemove: () => void }) {
  const kind = fileMediaKind(file.name);
  const [url, setUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  useEffect(() => {
    if (kind !== "image" && kind !== "audio") return;
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
          {issue && <p className="mt-1 text-xs text-red-700 dark:text-red-300">{issue}</p>}
        </div>
        <button type="button" title={`Remove ${file.name}`} aria-label={`Remove ${file.name}`} onClick={onRemove} disabled={disabled} className="shrink-0 rounded p-1 text-gray-500 hover:bg-gray-100 disabled:opacity-50"><X className="h-4 w-4" /></button>
      </div>
      {kind === "audio" && url && <audio controls preload="metadata" src={url} className="mt-2 h-9 w-full min-w-0" aria-label={`Preview ${file.name}`} onLoadedMetadata={(event) => { const seconds = event.currentTarget.duration; if (Number.isFinite(seconds) && seconds > 0) setDuration(seconds * 1000); }} />}
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

type ImportMode = "files" | "paste" | "urls" | "archive";

interface KnowledgePreview {
  source_count: number;
  concept_count: number;
  warnings: string[];
  documents: Array<{
    title: string;
    source_file: string;
    document_type: string;
    character_count: number;
    excerpt: string;
    media_kind: "document" | "image" | "audio";
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
  { id: "files", label: "Files", Icon: FileText },
  { id: "paste", label: "Paste Text", Icon: Clipboard },
  { id: "urls", label: "URLs", Icon: Globe },
] satisfies Array<{ id: ImportMode; label: string; Icon: typeof FileText }>;

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
  useEffect(() => { if (knowledgeFiles.some((file) => ["image", "audio"].includes(fileMediaKind(file.name) || ""))) setPreview(null); }, [capabilities, knowledgeFiles]);
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
    return files.length > 0;
  }, [files.length, mode, pastedText, urls.length]);
  const importSucceeded = importJob?.status === "succeeded";
  const importFailed = importJob?.status === "failed";

  const accept = mode === "archive" ? FILE_EXTENSIONS.archive : [FILE_EXTENSIONS.document, FILE_EXTENSIONS.archive,
    capabilities.status === "loaded" && capabilities.value.images.status === "ready" ? FILE_EXTENSIONS.image : "",
    capabilities.status === "loaded" && capabilities.value.audio.status === "ready" ? FILE_EXTENSIONS.audio : ""].filter(Boolean).join(",");
  const selectedBytes = files.reduce((total, file) => total + file.size, 0);
  const uploadIssue = mode === "files" && selectedBytes > MAX_UPLOAD_BYTES ? "Remove files to keep this upload at or below 50 MB." : null;
  const selectedIssues = mode === "files" || mode === "archive" ? [...files.map((file) => fileIssue(file, capabilities, mode === "archive")).filter(Boolean), ...(uploadIssue ? [uploadIssue] : [])] : [];

  const resetSource = (nextMode: ImportMode) => {
    setMode(nextMode);
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
    setError(rejected.length ? rejected.map((file) => `${file.name}: ${fileIssue(file, capabilities, mode === "archive")}`).join("; ") : null);
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
    if (assignAgentId) formData.append("assign_agent_id", String(assignAgentId));
    if (mode === "urls") {
      urls.forEach((url) => formData.append("urls", url));
    } else if (mode === "paste") {
      formData.append("pasted_text", pastedText.trim());
    } else {
      files.forEach((file) => formData.append("files", file));
    }
    return formData;
  };

  const handlePreview = async () => {
    if (!displayName.trim() || !hasSource || mode === "archive" || selectedIssues.length) return;

    try {
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
    if (importInFlight.current || !displayName.trim() || !hasSource || selectedIssues.length) return;
    importInFlight.current = true;
    const controller = new AbortController();
    startController.current = controller;

    try {
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
    if (!displayName.trim() || !hasSource || selectedIssues.length) return;
    if (mode !== "archive" && !preview) {
      await handlePreview();
      return;
    }
    await handleImport();
  };

  if (!portalHost) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex h-dvh w-screen items-center justify-center bg-black/50 p-4">
      <div role="dialog" aria-modal={true} aria-busy={importing || previewing} aria-labelledby={headingId} className="max-h-[92vh] w-full max-w-3xl overflow-hidden rounded-lg bg-white shadow-xl dark:bg-gray-800">
        <div className="flex items-center justify-between border-b border-gray-200 p-4 sm:p-6 dark:border-gray-700">
          <div>
            <h2 id={headingId} className="text-xl font-semibold text-gray-900 dark:text-white">
              Add Knowledge
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {teamSetupMode && teamName
                ? `Add local knowledge for ${teamName}.`
                : "Add files, text, or URLs."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Add Knowledge"
            disabled={importing || previewing}
            className="text-gray-400 hover:text-gray-500 disabled:opacity-50 dark:hover:text-gray-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="max-h-[calc(92vh-90px)] overflow-y-auto p-4 sm:p-6">
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-900" role="group" aria-label="Knowledge source">
            {MODE_OPTIONS.map(({ id, label, Icon }) => <button key={id} type="button" aria-pressed={mode === id} onClick={() => resetSource(id)} disabled={importing || previewing} className={`flex flex-1 items-center justify-center gap-2 rounded-md px-2 py-2 text-sm font-medium ${mode === id ? "bg-white text-emerald-800 shadow-sm dark:bg-gray-700 dark:text-emerald-200" : "text-gray-600 dark:text-gray-300"}`}><Icon className="h-4 w-4" />{label}</button>)}
          </div>
          <details className="mt-3 text-xs text-gray-500" open={mode === "archive" ? true : undefined}>
            <summary className="cursor-pointer">Advanced</summary>
            <button type="button" onClick={() => resetSource("archive")} disabled={importing || previewing} className={`mt-2 inline-flex items-center gap-2 rounded border px-3 py-2 ${mode === "archive" ? "border-emerald-500 text-emerald-700" : "border-gray-200"}`}><Archive className="h-4 w-4" />Prepared OKF archive</button>
          </details>

          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="knowledge-name" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Knowledge Name
              </label>
              <input
                id="knowledge-name"
                type="text"
                value={displayName}
                onChange={(event) => {
                  setDisplayName(event.target.value);
                  setPreview(null);
                }}
                disabled={importing || previewing}
                placeholder="e.g., Sales Playbook, HR Policy, Product FAQ"
                className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                required
              />
            </div>

            {teamAgentId && (
              <div>
                <label htmlFor="knowledge-visibility" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Visibility
                </label>
                <select
                  id="knowledge-visibility"
                value={visibility}
                  onChange={(event) => {
                    setVisibility(event.target.value);
                    setPreview(null);
                  }}
                  disabled={importing || previewing}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="team">Private (this team only)</option>
                  <option value="global">Global (all teams can use)</option>
                </select>
              </div>
            )}

            {mode === "urls" ? (
              <div>
                <label htmlFor="knowledge-urls" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Source URLs
                </label>
                <textarea
                  id="knowledge-urls"
                  value={urlText}
                  onChange={(event) => {
                    setUrlText(event.target.value);
                    setPreview(null);
                    setImportJob(null);
                    setError(null);
                  }}
                  disabled={importing || previewing}
                  rows={6}
                  placeholder={"https://example.com/policy\nhttps://example.com/faq"}
                  aria-describedby="knowledge-urls-hint"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
                <p id="knowledge-urls-hint" className="mt-1 text-xs text-gray-500">One public URL per line, up to 20. Only the listed pages are imported.</p>
              </div>
            ) : mode === "paste" ? (
              <div>
                <label htmlFor="knowledge-text" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Knowledge Text
                </label>
                <textarea
                  id="knowledge-text"
                  value={pastedText}
                  onChange={(event) => {
                    setPastedText(event.target.value);
                    setPreview(null);
                    setError(null);
                  }}
                  disabled={importing || previewing}
                  rows={10}
                  placeholder="Paste policy, FAQ, product information, SOP, or other knowledge here."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
            ) : (
              <div>
                {mode === "files" && <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {(["document", "image", "audio"] satisfies FileMediaKind[]).map((kind) => {
                    const capability = kind === "document" ? { status: "ready" } : capabilities.status === "loaded" ? (kind === "image" ? capabilities.value.images : capabilities.value.audio) : null;
                    const ready = capability?.status === "ready";
                    const Icon = kind === "image" ? ImageIcon : kind === "audio" ? Music2 : FileText;
                    const label = kind === "image" ? "Images" : kind === "audio" ? "Audio" : "Documents";
                    const status = ready ? "Ready" : capability?.status === "disabled" ? "Disabled" : capabilities.status === "loading" ? "Checking…" : "Unavailable";
                    return <label key={kind} className={`rounded-md border border-gray-200 p-3 dark:border-gray-600 ${ready && !importing && !previewing ? "cursor-pointer hover:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-2" : "opacity-60"}`}>
                      <span className="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-100"><Icon className="h-4 w-4" />{label}</span>
                      <span className="mt-1 block text-xs text-gray-500">{kind === "image" ? "JPG, PNG · 10 MB" : kind === "audio" ? "WAV, MP3 · 50 MB · 10 min" : "PDF, Office, text, archives · 50 MB"}</span>
                      <span className={`mt-1 block text-xs ${ready ? "text-emerald-700 dark:text-emerald-300" : "text-gray-500"}`}>{status}</span>
                      <input type="file" aria-label={`Add ${label.toLowerCase()}`} accept={kind === "document" ? `${FILE_EXTENSIONS.document},${FILE_EXTENSIONS.archive}` : FILE_EXTENSIONS[kind]} multiple disabled={!ready || importing || previewing} className="sr-only" onChange={(event) => { addFiles(event.target.files); event.currentTarget.value = ""; }} />
                    </label>;
                  })}
                </div>}
                {mode === "files" && <div className="mb-3 text-xs text-gray-500" aria-live="polite">
                  {capabilities.status === "unknown" ? "Media readiness unavailable. Documents are ready." : capabilities.status === "loaded" ? [capabilities.value.images, capabilities.value.audio].filter((item) => item.status === "unavailable").map((item) => item.status === "unavailable" ? item.reason : "").join(" · ") : ""}
                  {(capabilities.status === "unknown" || (capabilities.status === "loaded" && [capabilities.value.images, capabilities.value.audio].some((item) => item.status === "unavailable" && item.retryable))) && <button type="button" className="ml-2 text-emerald-700 underline" onClick={() => { setError(null); setReadinessRevision((value) => value + 1); }} disabled={importing || previewing}>Retry</button>}
                  {capabilities.status === "loaded" && capabilities.value.images.status === "ready" && <span className="block mt-1">{capabilities.value.image_ocr.status === "configured" ? "OCR configured" : "Optional OCR not configured"}</span>}
                </div>}
                <label className={`flex items-center justify-center gap-2 rounded-lg border-2 border-dashed p-4 text-sm text-gray-600 dark:text-gray-300 ${importing || previewing ? "opacity-60" : "cursor-pointer focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-2"} ${draggingFiles ? "border-emerald-500 bg-emerald-50" : "border-gray-300 dark:border-gray-600"}`}
                  onDragOver={(event) => { event.preventDefault(); if (!importing && !previewing) setDraggingFiles(true); }} onDragLeave={() => setDraggingFiles(false)} onDrop={(event) => { event.preventDefault(); setDraggingFiles(false); addFiles(event.dataTransfer.files); }}>
                  <input type="file" aria-label={mode === "archive" ? "Add prepared OKF archive" : "Add knowledge files"} accept={accept} multiple={mode !== "archive"} className="sr-only" disabled={importing || previewing} onChange={(event) => { addFiles(event.target.files); event.currentTarget.value = ""; }} />
                  <Upload className="h-5 w-5 shrink-0" />{mode === "archive" ? "Choose OKF archive · ZIP, TAR, TGZ" : "Drop files here or browse"}
                </label>
                {mode === "files" && <p className="mt-1 text-xs text-gray-500">50 MB total per upload</p>}
                {files.length > 0 && <div className="mt-3">
                  <div className="mb-2 flex items-center justify-between gap-2 text-xs text-gray-500"><span>{files.length} file{files.length === 1 ? "" : "s"} · {formatFileSize(selectedBytes)} selected</span><button type="button" onClick={clearFiles} disabled={importing || previewing} className="inline-flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-100"><Trash2 className="h-3.5 w-3.5" />Clear all</button></div>
                  {uploadIssue && <p role="alert" className="mb-2 text-sm text-red-700 dark:text-red-300">{uploadIssue}</p>}
                  <div className="max-h-72 space-y-2 overflow-y-auto">{files.map((file) => <FilePreview key={fileKey(file)} file={file} issue={fileIssue(file, capabilities, mode === "archive")} disabled={importing || previewing} onRemove={() => removeFile(file)} />)}</div>
                </div>}
              </div>
            )}

            {preview && mode !== "archive" && (
              <div className="rounded-lg border border-emerald-200 bg-white p-4 dark:border-emerald-900/50 dark:bg-gray-900">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                      Ready to create local knowledge
                    </h3>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                      {preview.source_count} source{preview.source_count === 1 ? "" : "s"} · {preview.concept_count} concept{preview.concept_count === 1 ? "" : "s"}
                    </p>
                  </div>
                </div>
                {preview.warnings.length > 0 && (
                  <details className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-100">
                    <summary className="cursor-pointer font-semibold">Review notes ({preview.warnings.length})</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {preview.warnings.map((warning, index) => (
                        <li key={`${warning}-${index}`}>{warning}</li>
                      ))}
                    </ul>
                  </details>
                )}
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
                      {document.text_status === "ready" && document.text && <details className="mt-2 text-xs text-gray-600 dark:text-gray-300"><summary className="cursor-pointer font-medium">{document.media_kind === "image" ? "Extracted image text" : "Extracted text"} · {document.character_count.toLocaleString()} characters</summary><pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded bg-gray-50 p-3 font-sans text-sm leading-6 dark:bg-gray-800">{document.text}</pre>{document.text_truncated && <p className="mt-1 text-gray-500">Preview limited to 12,000 characters.</p>}</details>}
                      {document.text_status !== "ready" && <p className="mt-2 text-xs text-gray-500">{document.media_kind === "audio" && document.text_status === "not_requested" ? "Transcript generated during import" : document.text_status === "unavailable" ? "Text extraction unavailable; original retained" : document.text_status === "not_requested" ? "OCR not requested; original retained" : "No readable text found"}</p>}

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
                      {importSucceeded ? "Local knowledge is ready" : importFailed ? "Import failed" : "Creating local knowledge"}
                    </h3>
                    <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
                      {importJob.message}
                    </p>
                    {importJob.bundle && (
                      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                        {importJob.bundle.concept_count} concept{importJob.bundle.concept_count === 1 ? "" : "s"} indexed
                        {importJob.bundle.tool_id ? " and capability created." : "."}
                      </p>
                    )}
                    {importSucceeded && teamSetupMode && (
                      <div className="mt-3 rounded-md border border-emerald-200 bg-white/70 p-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-gray-900/40 dark:text-emerald-100">
                        {assignAgentId
                          ? "This capability was assigned to the selected agent in this Team Agent. Return to the Team Agent to review or test the setup."
                          : "This capability is ready for this Team Agent. Return to the Team Agent and edit the agents that should use it."}
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
              <div className="rounded-md bg-red-50 p-4 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
                {error}
                {pendingImport.current && !importing && <button type="button" onClick={() => { void handleImport(); }} className="ml-3 font-medium underline">Retry status</button>}
              </div>
            )}
          </div>

          <div className="sticky bottom-0 mt-6 flex flex-wrap items-center justify-end gap-3 bg-white dark:bg-gray-800 border-t border-gray-200 pt-4 dark:border-gray-700">
            <button
              type="button"
              onClick={onClose}
              disabled={importing || previewing}
              className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              Cancel
            </button>
            {importSucceeded ? (
              <>
                {teamSetupMode && onReturnToTeam && (
                  <button
                    type="button"
                    onClick={onReturnToTeam}
                    className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
                  >
                    Back to Team Agent
                  </button>
                )}
                <button
                  type="button"
                  onClick={onClose}
                  className={[
                    "rounded-md px-4 py-2 text-sm font-medium",
                    teamSetupMode && onReturnToTeam
                      ? "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
                      : "bg-emerald-600 text-white hover:bg-emerald-700",
                  ].join(" ")}
                >
                  Done
                </button>
              </>
            ) : (
              <button
                type="submit"
                disabled={importing || previewing || !displayName.trim() || !hasSource || selectedIssues.length > 0}
                className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {(importing || previewing) && <Loader2 className="h-4 w-4 animate-spin" />}
                {mode === "archive" ? "Import OKF" : preview ? "Add Knowledge" : "Review Knowledge"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>,
    portalHost
  );
}
