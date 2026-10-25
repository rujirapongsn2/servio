"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Clock,
  Edit3,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Search,
  X,
} from "lucide-react";
import { KnowledgeAudio } from "@/components/KnowledgeAudio";
import { KnowledgeImages } from "@/components/KnowledgeImages";
import { KnowledgeDocumentImage } from "@/components/KnowledgeDocumentImage";
import { parseKnowledgeAudio, parseKnowledgeImages, type KnowledgeAudioClip, type KnowledgeImage } from "@/lib/product-presentations";
import { getApiBaseUrl } from "@/lib/api";

interface Tool {
  id: number;
  name: string;
  config: string | null;
  owner_team_name?: string | null;
  created_by_username?: string | null;
  agent_usage_count?: number;
}

interface OKFBundle {
  id: number;
  name: string;
  display_name: string;
  okf_version?: string | null;
  status: string;
  source_availability?: {
    status: "available" | "missing" | "partial" | "unreadable";
    missing_file_count: number;
    message: string | null;
  } | null;
  concept_count: number;
  link_count: number;
  validation_summary?: {
    warnings?: string[];
    error?: string;
    reindexed_at?: string;
    [key: string]: unknown;
  };
  visibility?: string | null;
  owner_team_name?: string | null;
  created_by_username?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface OKFConcept {
  id: number;
  bundle_id: number;
  concept_id: string;
  file_path: string;
  type: string;
  title?: string | null;
  description?: string | null;
  resource?: string | null;
  tags: string[];
  timestamp?: string | null;
  updated_at?: string | null;
  markdown?: string | null;
  frontmatter?: Record<string, unknown> | null;
  body?: string | null;
  has_image?: boolean;
  links: Array<{
    label?: string;
    target: string;
    target_concept_id?: string | null;
    is_external?: boolean;
    is_citation?: boolean;
    is_broken?: boolean;
  }>;
}

interface TestResult {
  images?: KnowledgeImage[];
  audio?: KnowledgeAudioClip[];
  response: string;
  response_time: number;
  concepts: Array<{
    concept_id: string;
    title?: string;
    type?: string;
    description?: string;
    excerpt?: string;
    score?: number;
    match_reason?: string;
  }>;
}

interface OKFBundleDetailDrawerProps {
  tool: Tool;
  teamAgentId?: number | null;
  onClose: () => void;
  onReindexed?: () => void;
  canEdit?: boolean;
}

type DetailTab = "overview" | "documents" | "ask" | "issues";

const formatDate = (value?: string | null) => {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2);

export default function OKFBundleDetailDrawer({
  tool,
  teamAgentId,
  onClose,
  onReindexed,
  canEdit = true,
}: OKFBundleDetailDrawerProps) {
  const apiBaseUrl = getApiBaseUrl();
  const config = useMemo(() => { try { const parsed = tool.config ? JSON.parse(tool.config) : {}; return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {}; } catch { return {}; } }, [tool.config]);
  const bundleId = config.okf_bundle_id as number | undefined;
  const displayName = (config.display_name as string | undefined) || tool.name;
  const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";

  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [bundle, setBundle] = useState<OKFBundle | null>(null);
  const [concepts, setConcepts] = useState<OKFConcept[]>([]);
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null);
  const [selectedConcept, setSelectedConcept] = useState<OKFConcept | null>(null);
  const [conceptQuery, setConceptQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [conceptLoading, setConceptLoading] = useState(false);
  const conceptRequest = useRef(0);
  const [reindexing, setReindexing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testQuery, setTestQuery] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [showAdvancedDetails, setShowAdvancedDetails] = useState(false);
  const [showImageText, setShowImageText] = useState(false);
  const [showRawIssues, setShowRawIssues] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEditingConcept, setIsEditingConcept] = useState(false);
  const [savingConcept, setSavingConcept] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editBody, setEditBody] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [refreshingSource, setRefreshingSource] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conceptError, setConceptError] = useState<string | null>(null);

  const warnings = bundle?.validation_summary?.warnings || [];
  const sourceIssue = bundle?.source_availability && bundle.source_availability.status !== "available"
    ? bundle.source_availability : null;
  const sourceUnavailable = Boolean(sourceIssue);
  const ready = bundle?.status === "ready" && !sourceUnavailable && warnings.length === 0;
  const issueCount = warnings.length + (sourceIssue ? 1 : 0);
  const statusLabel = sourceIssue
    ? sourceIssue.status === "partial" ? "Missing sources" : "Source unavailable"
    : bundle?.status;

  const filteredConcepts = useMemo(() => {
    const query = conceptQuery.trim().toLowerCase();
    if (!query) return concepts;
    return concepts.filter((concept) =>
      [
        concept.title,
        concept.concept_id,
        concept.file_path,
        concept.type,
        concept.description,
        concept.resource,
        ...(concept.tags || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [conceptQuery, concepts]);

  const loadBundle = async () => {
    if (!bundleId) return;
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("adminToken");
      const [bundleResponse, conceptsResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}${params}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/concepts${params}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (!bundleResponse.ok || !conceptsResponse.ok) {
        throw new Error("Failed to load local knowledge details");
      }

      const nextBundle: OKFBundle = await bundleResponse.json();
      const nextConcepts: OKFConcept[] = await conceptsResponse.json();
      setBundle(nextBundle);
      setConcepts(nextConcepts);
      setSelectedConceptId((current) => {
        if (current && nextConcepts.some((concept) => concept.concept_id === current)) return current;
        return nextConcepts[0]?.concept_id || null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load local knowledge details");
    } finally {
      setLoading(false);
    }
  };

  const loadConcept = async (conceptId: string | null) => {
    const request = ++conceptRequest.current;
    setConceptError(null);
    setSelectedConcept(null);
    if (!bundleId || !conceptId) {
      setConceptLoading(false);
      return;
    }
    setConceptLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/concepts/${encodeURIComponent(conceptId)}${params}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (request !== conceptRequest.current) return;
        if (response.status === 409) await loadBundle();
        throw new Error(response.status === 409 ? "This document's source file is unavailable." : typeof data.detail === "string" ? data.detail : "Failed to load concept detail");
      }
      const concept: OKFConcept = await response.json();
      if (request !== conceptRequest.current) return;
      setSelectedConcept(concept);
      setSourceUrl(typeof concept.frontmatter?.source_url === "string" ? concept.frontmatter.source_url : "");
      setEditTitle(concept.title || "");
      setEditDescription(concept.description || "");
      setEditTags((concept.tags || []).join(", "));
      setEditBody(concept.body || "");
    } catch (err) {
      if (request !== conceptRequest.current) return;
      setConceptError(err instanceof Error ? err.message : "Failed to load concept detail");
    } finally {
      if (request === conceptRequest.current) setConceptLoading(false);
    }
  };

  useEffect(() => {
    loadBundle();
  }, [bundleId, teamAgentId]);

  useEffect(() => {
    loadConcept(selectedConceptId);
    setShowAdvancedDetails(false);
    setShowImageText(false);
    setIsEditingConcept(false);
    setSaveMessage(null);
    setSaveError(null);
    return () => { conceptRequest.current += 1; };
  }, [selectedConceptId, bundleId, teamAgentId]);

  const handleReindex = async () => {
    if (!canEdit || sourceUnavailable) return;
    if (!bundleId) return;
    if (concepts.some((concept) => /^https?:\/\//i.test(concept.resource || "")) && !window.confirm("Re-fetch all URL sources? This replaces their content, including manual edits.")) return;
    setReindexing(true);
    setError(null);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/reindex${params}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (response.status === 503) {
          await loadBundle();
          await loadConcept(selectedConceptId);
        }
        throw new Error(data.detail || "Failed to re-index local knowledge");
      }
      await loadBundle();
      await loadConcept(selectedConceptId);
      onReindexed?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to re-index local knowledge");
    } finally {
      setReindexing(false);
    }
  };

  const handleRefreshSource = async () => {
    if (!canEdit || sourceUnavailable) return;
    if (!bundleId || !selectedConcept || !sourceUrl.trim()) return;
    if (!window.confirm("Fetch this URL again? Its content, including manual edits, will be replaced.")) return;
    setRefreshingSource(true);
    setSaveMessage(null);
    setSaveError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/reindex-source${params}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("adminToken")}` },
        body: JSON.stringify({ concept_id: selectedConcept.concept_id, url: sourceUrl.trim(), expected_updated_at: selectedConcept.updated_at }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (response.status === 503) {
          await loadBundle();
          await loadConcept(selectedConcept.concept_id);
        }
        throw new Error(data.detail || "Failed to refresh URL");
      }
      await loadBundle();
      await loadConcept(selectedConcept.concept_id);
      setIsEditingConcept(false);
      setSaveMessage("URL content replaced and re-indexed.");
      onReindexed?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to refresh URL");
    } finally {
      setRefreshingSource(false);
    }
  };

  const handleTest = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!bundleId || !testQuery.trim()) return;
    setTesting(true);
    setError(null);
    setTestResult(null);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/test${params}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query: testQuery }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to test local knowledge");
      }
      setTestResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to test local knowledge");
    } finally {
      setTesting(false);
    }
  };

  const openConceptFromResult = (conceptId: string) => {
    setSelectedConceptId(conceptId);
    setConceptQuery("");
    setShowAdvancedDetails(false);
    setActiveTab("documents");
  };

  const handleEditConcept = () => {
    if (!canEdit) return;
    if (!selectedConcept) return;
    setEditTitle(selectedConcept.title || "");
    setEditDescription(selectedConcept.description || "");
    setEditTags((selectedConcept.tags || []).join(", "));
    setEditBody(selectedConcept.body || "");
    setSaveMessage(null);
    setSaveError(null);
    setIsEditingConcept(true);
  };

  const handleCancelEdit = () => {
    if (!selectedConcept) return;
    setEditTitle(selectedConcept.title || "");
    setEditDescription(selectedConcept.description || "");
    setEditTags((selectedConcept.tags || []).join(", "));
    setEditBody(selectedConcept.body || "");
    setSaveMessage(null);
    setSaveError(null);
    setIsEditingConcept(false);
  };

  const handleSaveConcept = async () => {
    if (!canEdit || sourceUnavailable) return;
    if (!bundleId || !selectedConcept || (!selectedConcept.frontmatter?.audio && !editBody.trim())) return;
    setSavingConcept(true);
    setSaveMessage(null);
    setSaveError(null);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/concepts/${encodeURIComponent(selectedConcept.concept_id)}${params}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            title: editTitle,
            description: editDescription,
            tags: editTags
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
            body: editBody,
            expected_updated_at: selectedConcept.updated_at,
          }),
        },
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to save document");
      }
      const updatedConcept: OKFConcept = await response.json();
      setSelectedConcept(updatedConcept);
      setEditTitle(updatedConcept.title || "");
      setEditDescription(updatedConcept.description || "");
      setEditTags((updatedConcept.tags || []).join(", "));
      setEditBody(updatedConcept.body || "");
      setIsEditingConcept(false);
      setSaveMessage("Saved and re-indexed.");
      await loadBundle();
      onReindexed?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save document");
    } finally {
      setSavingConcept(false);
    }
  };

  const drawer = (
    <div role="dialog" aria-modal="true" aria-label="Knowledge details" tabIndex={-1} className="fixed inset-0 z-50 bg-black/40">
      <div className="absolute inset-y-0 right-0 flex w-full max-w-6xl flex-col bg-white shadow-2xl dark:bg-gray-900">
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 p-5 dark:border-gray-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-emerald-600" />
              <h2 className="truncate text-xl font-semibold text-gray-900 dark:text-white">
                {displayName}
              </h2>
              {bundle?.status && (
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${sourceIssue ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200" : "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200"}`}>
                  {statusLabel}
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleReindex}
              disabled={!canEdit || loading || sourceUnavailable || reindexing || refreshingSource || savingConcept || !bundleId}
              title={sourceIssue?.message || undefined}
              className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              {reindexing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Re-index
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="border-b border-gray-200 px-5 dark:border-gray-800">
          <div className="flex gap-1 overflow-x-auto">
            {[
              ["overview", "Overview"],
              ["documents", `Documents (${concepts.length})`],
              ["ask", "Ask a Question"],
              ["issues", issueCount > 0 ? `Issues (${issueCount})` : "Issues"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id as DetailTab)}
                className={[
                  "shrink-0 whitespace-nowrap border-b-2 px-3 py-3 text-sm font-semibold",
                  activeTab === id
                    ? "border-emerald-600 text-emerald-700 dark:text-emerald-300"
                    : "border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200",
                ].join(" ")}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {sourceIssue && (
            <div role="status" className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-100">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{sourceIssue.message}</span>
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center py-20 text-sm text-gray-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading knowledge details...
            </div>
          ) : error ? (
            <div className="rounded-md bg-red-50 p-4 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
              {error}
            </div>
          ) : (
            <>
              {activeTab === "overview" && (
                <div className="space-y-5">
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    <Metric label="Status" value={ready ? "Ready" : statusLabel || "N/A"} />
                    <Metric label="Documents" value={bundle?.concept_count ?? 0} />
                    <Metric label="Used by Agents" value={tool.agent_usage_count ?? 0} />
                    <Metric label="Last Updated" value={formatDate(bundle?.updated_at)} />
                  </div>

                  <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
                    <div className="flex items-start gap-3">
                      {ready ? (
                        <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                      ) : (
                        <AlertCircle className="mt-0.5 h-5 w-5 text-amber-600" />
                      )}
                      <div>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                          {ready
                            ? "This knowledge is ready to use"
                            : "This knowledge may need review"}
                        </h3>
                        <p className="mt-1 text-sm leading-6 text-gray-600 dark:text-gray-300">
                          {sourceIssue ? "Cached search results may still be available." : "Review documents or ask a question to check the available information."}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <InfoRow label="Owner Team" value={bundle?.owner_team_name || tool.owner_team_name || "N/A"} />
                    <InfoRow label="Added By" value={bundle?.created_by_username || tool.created_by_username || "N/A"} />
                  </div>
                </div>
              )}

              {activeTab === "documents" && (
                <div className="grid min-w-0 gap-4 lg:min-h-[560px] lg:grid-cols-[280px_minmax(0,1fr)]">
                  <div className="min-w-0 self-start overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800">
                    <div className="border-b border-gray-200 p-3 dark:border-gray-800">
                      <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                        <input
                          aria-label="Search documents"
                          value={conceptQuery}
                          onChange={(event) => setConceptQuery(event.target.value)}
                          placeholder="Search documents"
                          className="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                        />
                      </div>
                    </div>
                    <div className="max-h-[32dvh] overflow-y-auto lg:max-h-[620px]">
                      {filteredConcepts.map((concept) => (
                        <button
                          key={concept.concept_id}
                          type="button"
                          onClick={() => setSelectedConceptId(concept.concept_id)}
                          aria-pressed={selectedConceptId === concept.concept_id}
                          disabled={ refreshingSource || reindexing || savingConcept}
                          className={[
                            "block w-full border-b border-gray-100 p-3 text-left last:border-b-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800",
                            selectedConceptId === concept.concept_id ? "bg-emerald-50 dark:bg-emerald-900/20" : "",
                          ].join(" ")}
                        >
                          <div className="flex items-center gap-3">
                            {concept.has_image && bundleId && <KnowledgeDocumentImage bundleId={bundleId} conceptId={concept.concept_id} title={concept.title || concept.concept_id} teamAgentId={teamAgentId} thumbnail />}
                            <div className="min-w-0 flex-1">
                            <div className="line-clamp-1 text-sm font-semibold text-gray-900 dark:text-white">
                              {concept.title || concept.concept_id}
                            </div>
                          <div className="mt-1 line-clamp-1 text-xs text-gray-500">{concept.resource || concept.file_path}</div>
                          <div className="mt-2 flex flex-wrap gap-1">
                            {(concept.tags || []).slice(0, 2).map((tag) => (
                              <span key={tag} className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                {tag}
                              </span>
                            ))}
                          </div>
                            </div>
                          </div>
                        </button>
                      ))}
                      {filteredConcepts.length === 0 && (
                        <div className="p-6 text-center text-sm text-gray-500">No documents found.</div>
                      )}
                    </div>
                  </div>

                  <div className="min-w-0 rounded-lg border border-gray-200 dark:border-gray-800">
                    {conceptLoading ? (
                      <div className="flex items-center justify-center py-20 text-sm text-gray-500">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Loading document...
                      </div>
                    ) : conceptError ? (
                      <div role="alert" className="p-4 text-sm text-amber-800 dark:text-amber-200">{conceptError}</div>
                    ) : selectedConcept ? (
                      <div className="space-y-4 p-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <FileText className="h-4 w-4 text-emerald-600" />
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                              {selectedConcept.title || selectedConcept.concept_id}
                            </h3>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2 text-xs">
                            <span className="max-w-full break-all rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                              {selectedConcept.resource || selectedConcept.file_path}
                            </span>
                            {(selectedConcept.tags || []).slice(0, 3).map((tag) => (
                              <span key={tag} className="rounded-full bg-emerald-100 px-2.5 py-1 font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                {tag}
                              </span>
                            ))}
                            {selectedConcept.timestamp && (
                              <span className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                                Imported {formatDate(selectedConcept.timestamp)}
                              </span>
                            )}
                          </div>
                        </div>

                        {typeof selectedConcept.frontmatter?.source_url === "string" && (
                          <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-800">
                            <label htmlFor="document-source-url" className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">Source URL</label>
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <input id="document-source-url" type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} disabled={!canEdit || sourceUnavailable || refreshingSource || reindexing || savingConcept} className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white" />
                              <button type="button" onClick={handleRefreshSource} disabled={!canEdit || sourceUnavailable || refreshingSource || reindexing || savingConcept || !sourceUrl.trim()} className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200">
                                {refreshingSource ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Re-index URL
                              </button>
                            </div>
                            {typeof selectedConcept.frontmatter.fetched_at === "string" && <p className="mt-2 text-xs text-gray-500">Last fetched {formatDate(selectedConcept.frontmatter.fetched_at)}</p>}
                          </div>
                        )}

                        {selectedConcept.has_image && bundleId && <KnowledgeDocumentImage key={`${bundleId}:${selectedConcept.concept_id}`} bundleId={bundleId} conceptId={selectedConcept.concept_id} title={selectedConcept.title || selectedConcept.concept_id} teamAgentId={teamAgentId} />}

                        {selectedConcept.description && !selectedConcept.has_image && (
                          <div className="rounded-md bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                            {selectedConcept.description}
                          </div>
                        )}

                        {saveError && (
                          <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">{saveError}</div>
                        )}

                        <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
                          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
                            <div>
                              <div className="text-sm font-semibold text-gray-900 dark:text-white">
                                {selectedConcept.has_image ? <button type="button" onClick={() => setShowImageText((value) => !value)} aria-expanded={showImageText || isEditingConcept} aria-controls="knowledge-image-text" className="inline-flex items-center gap-2 rounded focus-visible:outline-emerald-500">
                                  Extracted text <ChevronDown className={`h-4 w-4 ${showImageText || isEditingConcept ? "rotate-180" : ""}`} aria-hidden="true" />
                                </button> : "Content Preview"}
                              </div>
                              {saveMessage && !isEditingConcept && (
                                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                                  <span>{saveMessage}</span>
                                  <button
                                    type="button"
                                    onClick={() => setActiveTab("ask")}
                                    className="inline-flex items-center gap-1 rounded-md border border-emerald-200 px-2 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900/50 dark:text-emerald-300 dark:hover:bg-emerald-900/20"
                                  >
                                    <Play className="h-3 w-3" />
                                    Test now
                                  </button>
                                </div>
                              )}
                            </div>
                            <div className="flex items-center gap-2">
                              {isEditingConcept ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={handleCancelEdit}
                                    disabled={!canEdit || savingConcept || refreshingSource || reindexing}
                                    className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
                                  >
                                    <X className="h-4 w-4" />
                                    Cancel
                                  </button>
                                  <button
                                    type="button"
                                    onClick={handleSaveConcept}
                                    disabled={!canEdit || sourceUnavailable || savingConcept || refreshingSource || reindexing || (!selectedConcept.frontmatter?.audio && !editBody.trim()) || !editTitle.trim()}
                                    className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                                  >
                                    {savingConcept ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                                    Save
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  onClick={handleEditConcept}
                                  disabled={!canEdit || sourceUnavailable || refreshingSource || reindexing}
                                  className="inline-flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
                                >
                                  <Edit3 className="h-4 w-4" />
                                  Edit
                                </button>
                              )}
                            </div>
                          </div>
                          {isEditingConcept ? (
                            <div id={selectedConcept.has_image ? "knowledge-image-text" : undefined} className="space-y-4 p-4">
                              <div className="grid gap-3 md:grid-cols-2">
                                <label className="block text-sm font-semibold text-gray-900 dark:text-white">
                                  Title
                                  <input
                                    value={editTitle}
                                    onChange={(event) => setEditTitle(event.target.value)}
                                    className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-normal focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                                  />
                                </label>
                                <label className="block text-sm font-semibold text-gray-900 dark:text-white">
                                  Tags
                                  <input
                                    value={editTags}
                                    onChange={(event) => setEditTags(event.target.value)}
                                    className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-normal focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                                  />
                                </label>
                              </div>
                              <label className="block text-sm font-semibold text-gray-900 dark:text-white">
                                Description
                                <input
                                  value={editDescription}
                                  onChange={(event) => setEditDescription(event.target.value)}
                                  className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-normal focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                                />
                              </label>
                              <label className="block text-sm font-semibold text-gray-900 dark:text-white">
                                {selectedConcept.frontmatter?.audio ? "Generated transcript (Re-index to refresh)" : "Content"}
                                <textarea
                                  aria-label={selectedConcept.frontmatter?.audio ? "Generated transcript" : "Content"}
                                  readOnly={Boolean(selectedConcept.frontmatter?.audio)}
                                  value={editBody}
                                  onChange={(event) => setEditBody(event.target.value)}
                                  rows={18}
                                  className="mt-2 w-full resize-y rounded-md border border-gray-300 px-3 py-3 font-mono text-sm leading-6 focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
                                />
                              </label>
                            </div>
                          ) : (!selectedConcept.has_image || showImageText) && (
                            <div id={selectedConcept.has_image ? "knowledge-image-text" : undefined} className="max-h-[520px] overflow-y-auto whitespace-pre-wrap p-4 text-sm leading-7 text-gray-800 dark:text-gray-100">
                              {selectedConcept.body || "No readable content found."}
                            </div>
                          )}
                        </div>

                        <div className="rounded-lg border border-gray-200 dark:border-gray-800">
                          <button
                            type="button"
                            onClick={() => setShowAdvancedDetails((value) => !value)}
                            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-gray-900 hover:bg-gray-50 dark:text-white dark:hover:bg-gray-800"
                          >
                            Advanced details
                            <span className="text-xs font-medium text-gray-500">
                              {showAdvancedDetails ? "Hide" : "Show"}
                            </span>
                          </button>
                          {showAdvancedDetails && (
                            <div className="space-y-4 border-t border-gray-200 p-4 dark:border-gray-800">
                              <div className="grid gap-3 md:grid-cols-2">
                                <InfoRow label="Document Path" value={selectedConcept.file_path} />
                                <InfoRow label="Document ID" value={selectedConcept.concept_id} />
                              </div>
                              <div className="grid gap-4 xl:grid-cols-2">
                                <CodePanel title="Metadata" content={formatJson(selectedConcept.frontmatter)} />
                                <CodePanel title="Markdown" content={selectedConcept.markdown || ""} />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="p-8 text-center text-sm text-gray-500">Select a document to preview.</div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === "ask" && (
                <div className="space-y-5">
                  <form onSubmit={handleTest} className="space-y-3">
                    <label htmlFor="workflow-knowledge-question" className="block text-sm font-semibold text-gray-900 dark:text-white">
                      Ask a question
                    </label>
                    <textarea
                      id="workflow-knowledge-question"
                      value={testQuery}
                      onChange={(event) => setTestQuery(event.target.value)}
                      rows={3}
                      placeholder="Example: What does this policy say about refunds?"
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                    />
                    <button
                      type="submit"
                      disabled={testing || !testQuery.trim()}
                      className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      Ask
                    </button>
                  </form>

                  {testResult && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Clock className="h-4 w-4" />
                        {testResult.response_time.toFixed(2)}s
                      </div>
                      <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
                        <div className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900 dark:border-gray-800 dark:text-white">
                          Answer
                        </div>
                        <div className="whitespace-pre-wrap p-4 text-sm leading-6 text-gray-800 dark:text-gray-100">
                          {testResult.response}
                        </div>
                      </div>
                      {testResult.images && <KnowledgeImages images={parseKnowledgeImages({ type: "knowledge_images", version: 1, response: testResult.response, images: testResult.images })?.images || []} />}
                      <KnowledgeAudio audio={parseKnowledgeAudio(testResult.audio)} />
                      <div className="space-y-2">
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                          Sources Used ({testResult.concepts.length})
                        </h3>
                        {testResult.concepts.map((concept) => (
                          <button
                            key={concept.concept_id}
                            type="button"
                            onClick={() => openConceptFromResult(concept.concept_id)}
                            className="block w-full rounded-md border border-emerald-200 bg-emerald-50 p-3 text-left transition hover:border-emerald-400 hover:bg-emerald-100 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:hover:bg-emerald-900/35"
                          >
                            <div className="text-sm font-semibold text-gray-900 dark:text-white">
                              {concept.title || concept.concept_id}
                            </div>
                            {(concept.description || concept.excerpt) && (
                              <p className="mt-2 line-clamp-3 text-sm text-gray-700 dark:text-gray-200">
                                {concept.description || concept.excerpt}
                              </p>
                            )}
                            <div className="mt-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                              View document
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === "issues" && (
                <div className="space-y-4">
                  {ready && !bundle?.validation_summary?.error && (
                    <div className="flex items-start gap-3 rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-100">
                      <CheckCircle2 className="mt-0.5 h-5 w-5" />
                      No issues found. This knowledge is ready for agents to use.
                    </div>
                  )}
                  {bundle?.validation_summary?.error && (
                    <div className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-100">
                      <AlertCircle className="mt-0.5 h-5 w-5" />
                      {bundle.validation_summary.error}
                    </div>
                  )}
                  {warnings.map((warning, index) => (
                    <div key={`${warning}-${index}`} className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-100">
                      <AlertCircle className="mt-0.5 h-5 w-5" />
                      {warning}
                    </div>
                  ))}
                  <div className="rounded-lg border border-gray-200 dark:border-gray-800">
                    <button
                      type="button"
                      onClick={() => setShowRawIssues((value) => !value)}
                      className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-gray-900 hover:bg-gray-50 dark:text-white dark:hover:bg-gray-800"
                    >
                      Advanced issue details
                      <span className="text-xs font-medium text-gray-500">
                        {showRawIssues ? "Hide" : "Show"}
                      </span>
                    </button>
                    {showRawIssues && (
                      <div className="border-t border-gray-200 p-4 dark:border-gray-800">
                        <CodePanel title="Issue Metadata" content={formatJson(bundle?.validation_summary || {})} />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
  return typeof document !== "undefined" && document.body ? createPortal(drawer, document.body) : drawer;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-2 break-words text-sm font-medium text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

function CodePanel({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-800">
      <div className="border-b border-gray-200 px-3 py-2 text-sm font-semibold text-gray-900 dark:border-gray-800 dark:text-white">
        {title}
      </div>
      <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words bg-gray-950 p-3 text-xs leading-5 text-gray-100">
        {content || "N/A"}
      </pre>
    </div>
  );
}
