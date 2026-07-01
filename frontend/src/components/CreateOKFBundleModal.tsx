"use client";

import { useMemo, useState } from "react";
import { AlertCircle, Archive, CheckCircle2, Clipboard, FileText, Loader2, Plus, Trash2, Upload, X } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface CreateOKFBundleModalProps {
  teamAgentId?: number | null;
  assignAgentId?: number | null;
  teamSetupMode?: boolean;
  teamName?: string | null;
  onClose: () => void;
  onSuccess: () => void;
  onReturnToTeam?: () => void;
}

type ImportMode = "files" | "paste" | "archive";

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

const MODE_OPTIONS: Array<{
  id: ImportMode;
  label: string;
  description: string;
}> = [
  {
    id: "files",
    label: "Upload Files",
    description: "PDF, Word, text, Markdown, CSV, JSON, HTML, or ZIP folders.",
  },
  {
    id: "paste",
    label: "Paste Text",
    description: "Paste policies, FAQs, product notes, or SOP content directly.",
  },
  {
    id: "archive",
    label: "Advanced OKF",
    description: "Import a prepared OKF archive for technical users.",
  },
];

export default function CreateOKFBundleModal({
  teamAgentId,
  assignAgentId,
  teamSetupMode = false,
  teamName,
  onClose,
  onSuccess,
  onReturnToTeam,
}: CreateOKFBundleModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [displayName, setDisplayName] = useState("");
  const [visibility, setVisibility] = useState("team");
  const [mode, setMode] = useState<ImportMode>("files");
  const [files, setFiles] = useState<File[]>([]);
  const [pastedText, setPastedText] = useState("");
  const [importing, setImporting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [draggingFiles, setDraggingFiles] = useState(false);
  const [preview, setPreview] = useState<KnowledgePreview | null>(null);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasSource = useMemo(() => {
    if (mode === "paste") return pastedText.trim().length > 0;
    return files.length > 0;
  }, [files.length, mode, pastedText]);
  const importSucceeded = importJob?.status === "succeeded";
  const importFailed = importJob?.status === "failed";

  const fileHint =
    mode === "archive"
      ? "ZIP, TAR, TAR.GZ, or TGZ containing OKF Markdown files"
      : "PDF, DOCX, TXT, MD, CSV, JSON, HTML, ZIP, TAR, TAR.GZ, or TGZ up to 50MB";

  const accept =
    mode === "archive"
      ? ".zip,.tar,.gz,.tgz"
      : ".pdf,.docx,.txt,.md,.markdown,.csv,.tsv,.json,.html,.htm,.zip,.tar,.gz,.tgz";

  const resetSource = (nextMode: ImportMode) => {
    setMode(nextMode);
    setFiles([]);
    setPastedText("");
    setPreview(null);
    setImportJob(null);
    setError(null);
  };

  const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

  const addFiles = (nextFiles: FileList | File[] | null) => {
    const selected = Array.from(nextFiles || []);
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
      return mode === "archive" ? merged.slice(-1) : merged;
    });
    setPreview(null);
    setError(null);
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
    formData.append("import_mode", mode === "archive" ? "archive" : "knowledge");
    formData.append("create_tool", "true");
    if (assignAgentId) formData.append("assign_agent_id", String(assignAgentId));
    if (mode === "paste") {
      formData.append("pasted_text", pastedText.trim());
    } else {
      files.forEach((file) => formData.append("files", file));
    }
    return formData;
  };

  const handlePreview = async () => {
    if (!displayName.trim() || !hasSource || mode === "archive") return;

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
    if (!displayName.trim() || !hasSource) return;

    try {
      setImporting(true);
      setImportJob(null);
      setError(null);
      const token = localStorage.getItem("adminToken");
      const formData = buildFormData();

      const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/import-jobs${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to add knowledge");
      }

      const job: ImportJob = await response.json();
      setImportJob(job);
      await pollImportJob(job.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add knowledge");
      setImporting(false);
    }
  };

  const pollImportJob = async (jobId: string) => {
    const token = localStorage.getItem("adminToken");
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 900));
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/import-jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to read import job status");
      }
      const job: ImportJob = await response.json();
      setImportJob(job);
      if (job.status === "succeeded") {
        setImporting(false);
        onSuccess();
        return;
      }
      if (job.status === "failed") {
        setImporting(false);
        setError(job.error || "Failed to add knowledge");
        return;
      }
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!displayName.trim() || !hasSource) return;
    if (mode !== "archive" && !preview) {
      await handlePreview();
      return;
    }
    await handleImport();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-hidden rounded-lg bg-white shadow-xl dark:bg-gray-800">
        <div className="flex items-center justify-between border-b border-gray-200 p-6 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Add Knowledge
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {teamSetupMode && teamName
                ? `Add local knowledge for ${teamName}.`
                : "Upload everyday files and Servio will convert them into local OKF knowledge."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={importing}
            className="text-gray-400 hover:text-gray-500 disabled:opacity-50 dark:hover:text-gray-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="max-h-[calc(92vh-90px)] overflow-y-auto p-6">
          <div className="grid gap-3 md:grid-cols-3">
            {MODE_OPTIONS.map((option) => {
              const active = option.id === mode;
              const Icon = option.id === "files" ? FileText : option.id === "paste" ? Clipboard : Archive;
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => resetSource(option.id)}
                  disabled={importing}
                  className={[
                    "rounded-lg border p-4 text-left transition disabled:opacity-50",
                    active
                      ? "border-emerald-500 bg-emerald-50 text-emerald-950 dark:border-emerald-400 dark:bg-emerald-900/20 dark:text-emerald-100"
                      : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200",
                  ].join(" ")}
                >
                  <Icon className={active ? "mb-3 h-5 w-5 text-emerald-600" : "mb-3 h-5 w-5 text-gray-400"} />
                  <div className="text-sm font-semibold">{option.label}</div>
                  <div className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
                    {option.description}
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-6 space-y-5">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Knowledge Name
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(event) => {
                  setDisplayName(event.target.value);
                  setPreview(null);
                }}
                disabled={importing}
                placeholder="e.g., Sales Playbook, HR Policy, Product FAQ"
                className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                required
              />
            </div>

            {teamAgentId && (
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Visibility
                </label>
                <select
                value={visibility}
                  onChange={(event) => {
                    setVisibility(event.target.value);
                    setPreview(null);
                  }}
                  disabled={importing}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                >
                  <option value="team">Private (this team only)</option>
                  <option value="global">Global (all teams can use)</option>
                </select>
              </div>
            )}

            {mode === "paste" ? (
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Knowledge Text
                </label>
                <textarea
                  value={pastedText}
                  onChange={(event) => {
                    setPastedText(event.target.value);
                    setPreview(null);
                    setError(null);
                  }}
                  disabled={importing}
                  rows={10}
                  placeholder="Paste policy, FAQ, product information, SOP, or other knowledge here."
                  className="w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-emerald-500 focus:ring-emerald-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                />
              </div>
            ) : (
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {mode === "archive" ? "OKF Archive" : "Knowledge Files"}
                </label>
                <label
                  className={[
                    "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 transition",
                    draggingFiles
                      ? "border-emerald-500 bg-emerald-50 dark:border-emerald-400 dark:bg-emerald-900/20"
                      : "border-gray-300 hover:bg-emerald-50 dark:border-gray-600 dark:hover:bg-emerald-900/10",
                  ].join(" ")}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!importing) setDraggingFiles(true);
                  }}
                  onDragLeave={() => setDraggingFiles(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDraggingFiles(false);
                    if (!importing) addFiles(event.dataTransfer.files);
                  }}
                >
                  <input
                    type="file"
                    accept={accept}
                    multiple={mode !== "archive"}
                    className="hidden"
                    disabled={importing}
                    onChange={(event) => {
                      addFiles(event.target.files);
                      event.currentTarget.value = "";
                    }}
                  />
                  <Upload className={files.length > 0 ? "h-10 w-10 text-emerald-600" : "h-10 w-10 text-gray-400"} />
                  <div className="text-center">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {files.length > 0
                        ? `${files.length} file${files.length > 1 ? "s" : ""} selected`
                        : mode === "archive"
                          ? "Click to upload a prepared OKF archive"
                          : "Click to upload knowledge files"}
                    </p>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{fileHint}</p>
                    {mode !== "archive" && (
                      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                        Select multiple files at once, or click again to add more into the same Knowledge.
                      </p>
                    )}
                  </div>
                </label>
                {files.length > 0 && (
                  <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-2 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                    <div className="mb-2 flex items-center justify-between gap-3 px-1">
                      <span className="font-medium text-gray-700 dark:text-gray-200">
                        {files.length} file{files.length > 1 ? "s" : ""} in this Knowledge
                      </span>
                      <button
                        type="button"
                        onClick={clearFiles}
                        disabled={importing}
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-gray-500 hover:bg-gray-200 hover:text-gray-700 disabled:opacity-50 dark:hover:bg-gray-700 dark:hover:text-gray-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Clear all
                      </button>
                    </div>
                    <div className="max-h-36 overflow-y-auto">
                      {files.map((file) => (
                        <div key={fileKey(file)} className="flex items-center justify-between gap-3 rounded px-2 py-1.5 hover:bg-white dark:hover:bg-gray-800">
                          <span className="truncate">{file.name}</span>
                          <div className="flex shrink-0 items-center gap-3">
                            <span className="text-gray-400">{Math.max(1, Math.round(file.size / 1024))} KB</span>
                            <button
                              type="button"
                              onClick={() => removeFile(file)}
                              disabled={importing}
                              className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-900/20 dark:hover:text-red-300"
                              aria-label={`Remove ${file.name}`}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {mode !== "archive" && (
                      <label className="mt-2 inline-flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-900/20">
                        <input
                          type="file"
                          accept={accept}
                          multiple
                          className="hidden"
                          disabled={importing}
                          onChange={(event) => {
                            addFiles(event.target.files);
                            event.currentTarget.value = "";
                          }}
                        />
                        <Plus className="h-3.5 w-3.5" />
                        Add more files
                      </label>
                    )}
                  </div>
                )}
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
                      {preview.source_count} readable document{preview.source_count === 1 ? "" : "s"} will become {preview.concept_count} OKF concept{preview.concept_count === 1 ? "" : "s"}.
                    </p>
                  </div>
                </div>
                {preview.warnings.length > 0 && (
                  <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-100">
                    <div className="font-semibold">Review notes</div>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                      {preview.warnings.slice(0, 5).map((warning, index) => (
                        <li key={`${warning}-${index}`}>{warning}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="mt-4 max-h-52 space-y-2 overflow-y-auto">
                  {preview.documents.slice(0, 8).map((document) => (
                    <div key={`${document.source_file}-${document.character_count}`} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-gray-900 dark:text-white">{document.title}</div>
                          <div className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">{document.source_file}</div>
                        </div>
                        <span className="shrink-0 rounded-full bg-gray-100 px-2 py-1 text-[11px] font-medium uppercase text-gray-600 dark:bg-gray-700 dark:text-gray-200">
                          {document.document_type}
                        </span>
                      </div>
                      {document.excerpt && (
                        <p className="mt-2 line-clamp-2 text-xs leading-5 text-gray-500 dark:text-gray-400">{document.excerpt}</p>
                      )}
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

            {mode !== "archive" && (
              <div className="flex gap-3 rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-100">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <p>
                  {teamSetupMode
                    ? "You do not need to prepare OKF files. Servio will create local knowledge, build an agent capability, and keep you in this Team Agent setup flow."
                    : "You do not need to prepare OKF files. Servio will extract readable text, generate Markdown with YAML metadata, store it locally, and index it for agents."}
                </p>
              </div>
            )}

            {error && (
              <div className="rounded-md bg-red-50 p-4 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
                {error}
              </div>
            )}
          </div>

          <div className="mt-6 flex items-center justify-end gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
            <button
              type="button"
              onClick={onClose}
              disabled={importing}
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
                disabled={importing || previewing || !displayName.trim() || !hasSource}
                className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {(importing || previewing) && <Loader2 className="h-4 w-4 animate-spin" />}
                {mode === "archive" ? "Import OKF" : preview ? "Add Knowledge" : "Review Knowledge"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
