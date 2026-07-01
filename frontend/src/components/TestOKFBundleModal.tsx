"use client";

import { useState } from "react";
import { X, Play, Loader2, Clock, BookOpen, Link as LinkIcon } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface Tool {
  id: number;
  name: string;
  config: string | null;
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
    links?: Array<{
      label?: string;
      target: string;
      is_citation?: boolean;
      is_broken?: boolean;
    }>;
  }>;
}

interface TestOKFBundleModalProps {
  tool: Tool;
  teamAgentId?: number | null;
  onClose: () => void;
}

export default function TestOKFBundleModal({
  tool,
  teamAgentId,
  onClose,
}: TestOKFBundleModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const config = tool.config ? JSON.parse(tool.config) : {};
  const bundleId = config.okf_bundle_id;
  const displayName = config.display_name || tool.name;
  const [query, setQuery] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTest = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim() || !bundleId) return;

    try {
      setTesting(true);
      setError(null);
      setResult(null);
      const token = localStorage.getItem("adminToken");
      const params = teamAgentId ? `?team_agent_id=${teamAgentId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/okf-bundles/${bundleId}/test${params}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to test OKF bundle");
      }

      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to test OKF bundle");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Test OKF Knowledge - {displayName}
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Query local Markdown/YAML knowledge without cloud file search
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={testing}
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          <form onSubmit={handleTest} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Query
              </label>
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                disabled={testing}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white disabled:opacity-50"
                placeholder="Ask about the OKF knowledge bundle..."
                required
              />
            </div>

            <button
              type="submit"
              disabled={testing || !query.trim() || !bundleId}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run Query
            </button>
          </form>

          {error && (
            <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-800 dark:text-red-300">
              {error}
            </div>
          )}

          {result && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <Clock className="w-4 h-4" />
                <span>Response time: {result.response_time.toFixed(2)}s</span>
              </div>

              <div className="rounded-md bg-gray-50 dark:bg-gray-900 p-4 border border-gray-200 dark:border-gray-700">
                <p className="text-sm text-gray-900 dark:text-white whitespace-pre-wrap">
                  {result.response}
                </p>
              </div>

              {result.concepts.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white">
                    Matching Concepts ({result.concepts.length})
                  </h3>
                  {result.concepts.map((concept) => (
                    <div
                      key={concept.concept_id}
                      className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 p-4"
                    >
                      <div className="flex items-start gap-3">
                        <BookOpen className="w-4 h-4 text-emerald-700 dark:text-emerald-300 mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-sm font-medium text-gray-900 dark:text-white">
                              {concept.title || concept.concept_id}
                            </p>
                            {concept.type && (
                              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-white/70 dark:bg-gray-900/50 text-emerald-800 dark:text-emerald-200">
                                {concept.type}
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                            {concept.concept_id}
                          </p>
                          {(concept.description || concept.excerpt) && (
                            <p className="mt-2 text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                              {concept.description || concept.excerpt}
                            </p>
                          )}
                          {concept.links && concept.links.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              {concept.links.slice(0, 5).map((link, index) => (
                                <span
                                  key={`${link.target}-${index}`}
                                  className="inline-flex items-center gap-1 px-2 py-1 rounded bg-white/70 dark:bg-gray-900/50 text-xs text-gray-700 dark:text-gray-300"
                                >
                                  <LinkIcon className="w-3 h-3" />
                                  {link.label || link.target}
                                  {link.is_broken ? " (broken)" : ""}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={onClose}
            disabled={testing}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md disabled:opacity-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
