"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  Play,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
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
}: OKFBundleDetailDrawerProps) {
  const apiBaseUrl = getApiBaseUrl();
  const config = useMemo(() => (tool.config ? JSON.parse(tool.config) : {}), [tool.config]);
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
  const [reindexing, setReindexing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testQuery, setTestQuery] = useState("");
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [showAdvancedDetails, setShowAdvancedDetails] = useState(false);
  const [showRawIssues, setShowRawIssues] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const warnings = bundle?.validation_summary?.warnings || [];

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
      setSelectedConceptId((current) => current || nextConcepts[0]?.concept_id || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load local knowledge details");
    } finally {
      setLoading(false);
    }
  };

  const loadConcept = async (conceptId: string | null) => {
    if (!bundleId || !conceptId) {
      setSelectedConcept(null);
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
      if (!response.ok) throw new Error("Failed to load concept detail");
      setSelectedConcept(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load concept detail");
    } finally {
      setConceptLoading(false);
    }
  };

  useEffect(() => {
    loadBundle();
  }, [bundleId, teamAgentId]);

  useEffect(() => {
    loadConcept(selectedConceptId);
    setShowAdvancedDetails(false);
  }, [selectedConceptId, bundleId, teamAgentId]);

  const handleReindex = async () => {
    if (!bundleId) return;
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
        throw new Error(data.detail || "Failed to re-index local knowledge");
      }
      await loadBundle();
      onReindexed?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to re-index local knowledge");
    } finally {
      setReindexing(false);
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

  return (
    <div className="fixed inset-0 z-50 bg-black/40">
      <div className="absolute inset-y-0 right-0 flex w-full max-w-6xl flex-col bg-white shadow-2xl dark:bg-gray-900">
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 p-5 dark:border-gray-800">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-emerald-600" />
              <h2 className="truncate text-xl font-semibold text-gray-900 dark:text-white">
                {displayName}
              </h2>
              {bundle?.status && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200">
                  {bundle.status}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Review documents, ask a question, and check whether this knowledge is ready for agents.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={handleReindex}
              disabled={reindexing || !bundleId}
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
              ["issues", warnings.length > 0 ? `Issues (${warnings.length})` : "Issues"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id as DetailTab)}
                className={[
                  "border-b-2 px-3 py-3 text-sm font-semibold",
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
                    <Metric label="Status" value={bundle?.status === "ready" ? "Ready" : bundle?.status || "N/A"} />
                    <Metric label="Documents" value={bundle?.concept_count ?? 0} />
                    <Metric label="Used by Agents" value={tool.agent_usage_count ?? 0} />
                    <Metric label="Last Updated" value={formatDate(bundle?.updated_at)} />
                  </div>

                  <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
                    <div className="flex items-start gap-3">
                      {bundle?.status === "ready" && warnings.length === 0 ? (
                        <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                      ) : (
                        <AlertCircle className="mt-0.5 h-5 w-5 text-amber-600" />
                      )}
                      <div>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                          {bundle?.status === "ready" && warnings.length === 0
                            ? "This knowledge is ready to use"
                            : "This knowledge may need review"}
                        </h3>
                        <p className="mt-1 text-sm leading-6 text-gray-600 dark:text-gray-300">
                          Agents can search these documents when answering questions. Use Documents to review the readable content, or Ask a Question to check whether the expected information can be found.
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
                <div className="grid min-h-[560px] gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
                  <div className="rounded-lg border border-gray-200 dark:border-gray-800">
                    <div className="border-b border-gray-200 p-3 dark:border-gray-800">
                      <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                        <input
                          value={conceptQuery}
                          onChange={(event) => setConceptQuery(event.target.value)}
                          placeholder="Search documents"
                          className="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-emerald-500 focus:ring-emerald-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                        />
                      </div>
                    </div>
                    <div className="max-h-[620px] overflow-y-auto">
                      {filteredConcepts.map((concept) => (
                        <button
                          key={concept.concept_id}
                          type="button"
                          onClick={() => setSelectedConceptId(concept.concept_id)}
                          className={[
                            "block w-full border-b border-gray-100 p-3 text-left last:border-b-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800",
                            selectedConceptId === concept.concept_id ? "bg-emerald-50 dark:bg-emerald-900/20" : "",
                          ].join(" ")}
                        >
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
                        </button>
                      ))}
                      {filteredConcepts.length === 0 && (
                        <div className="p-6 text-center text-sm text-gray-500">No documents found.</div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-gray-200 dark:border-gray-800">
                    {conceptLoading ? (
                      <div className="flex items-center justify-center py-20 text-sm text-gray-500">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Loading document...
                      </div>
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
                            <span className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200">
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

                        {selectedConcept.description && (
                          <div className="rounded-md bg-gray-50 p-3 text-sm text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                            {selectedConcept.description}
                          </div>
                        )}

                        <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
                          <div className="border-b border-gray-200 px-4 py-3 text-sm font-semibold text-gray-900 dark:border-gray-800 dark:text-white">
                            Content Preview
                          </div>
                          <div className="max-h-[520px] overflow-y-auto whitespace-pre-wrap p-4 text-sm leading-7 text-gray-800 dark:text-gray-100">
                            {selectedConcept.body || "No readable content found."}
                          </div>
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
                    <label className="block text-sm font-semibold text-gray-900 dark:text-white">
                      Ask a question
                    </label>
                    <textarea
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
                  {bundle?.status === "ready" && warnings.length === 0 && !bundle.validation_summary?.error && (
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
