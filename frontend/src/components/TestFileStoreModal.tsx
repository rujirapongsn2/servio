"use client";

import { useState } from "react";
import { X, Play, Loader2, FileText, Clock } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface FileStore {
  id: number;
  name: string;
  gemini_store_id: string;
  display_name: string;
  file_count: number;
  created_at: string;
}

interface TestResult {
  response: string;
  grounding_sources: string[];
  metadata?: Record<string, unknown>;
  response_time: number;
}

interface TestFileStoreModalProps {
  store: FileStore;
  onClose: () => void;
}

export default function TestFileStoreModal({
  store,
  onClose,
}: TestFileStoreModalProps) {
  const apiBaseUrl = getApiBaseUrl();
  const [query, setQuery] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTest = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!query.trim()) {
      alert("Please enter a query");
      return;
    }

    try {
      setTesting(true);
      setError(null);
      setResult(null);

      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/file-stores/${store.id}/test`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ query }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to test file store");
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Failed to test file store:", err);
      setError(err instanceof Error ? err.message : "Failed to test file store");
    } finally {
      setTesting(false);
    }
  };

  const handleReset = () => {
    setQuery("");
    setResult(null);
    setError(null);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Test File Store - {store.display_name}
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Query the file store and see detailed results with grounding sources
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
          {/* Store Information */}
          <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600 dark:text-gray-400">Store Name:</span>
                <span className="ml-2 font-medium text-gray-900 dark:text-white">
                  {store.name}
                </span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">Files:</span>
                <span className="ml-2 font-medium text-gray-900 dark:text-white">
                  {store.file_count} file{store.file_count !== 1 ? "s" : ""}
                </span>
              </div>
            </div>
          </div>

          {/* Query Form */}
          <form onSubmit={handleTest} className="space-y-4">
            <div>
              <label
                htmlFor="query"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
              >
                Query
              </label>
              <textarea
                id="query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={testing}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white disabled:opacity-50"
                placeholder="Enter your question about the documents..."
                required
              />
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Ask any question about the content in this file store
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={testing || !query.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {testing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Testing...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4" />
                    Run Query
                  </>
                )}
              </button>

              {result && (
                <button
                  type="button"
                  onClick={handleReset}
                  disabled={testing}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md disabled:opacity-50"
                >
                  Clear Results
                </button>
              )}
            </div>
          </form>

          {/* Error Display */}
          {error && (
            <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 border border-red-200 dark:border-red-800">
              <div className="flex">
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                    Error
                  </h3>
                  <div className="mt-2 text-sm text-red-700 dark:text-red-400">
                    {error}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Results Display */}
          {result && (
            <div className="space-y-4">
              {/* Response Time */}
              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <Clock className="w-4 h-4" />
                <span>Response time: {result.response_time.toFixed(2)}s</span>
              </div>

              {/* Main Response */}
              <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                  Response
                </h3>
                <div className="rounded-md bg-gray-50 dark:bg-gray-900 p-4 border border-gray-200 dark:border-gray-700">
                  <p className="text-sm text-gray-900 dark:text-white whitespace-pre-wrap">
                    {result.response}
                  </p>
                </div>
              </div>

              {/* Grounding Sources */}
              {result.grounding_sources && result.grounding_sources.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                    Grounding Sources ({result.grounding_sources.length})
                  </h3>
                  <div className="space-y-2">
                    {result.grounding_sources.map((source, index) => (
                      <div
                        key={index}
                        className="rounded-md bg-blue-50 dark:bg-blue-900/20 p-3 border border-blue-200 dark:border-blue-800"
                      >
                        <div className="flex items-start gap-2">
                          <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                          <p className="text-sm text-gray-900 dark:text-white">
                            {source}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              {result.metadata && Object.keys(result.metadata).length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
                    Metadata
                  </h3>
                  <div className="rounded-md bg-gray-50 dark:bg-gray-900 p-4 border border-gray-200 dark:border-gray-700">
                    <pre className="text-xs text-gray-900 dark:text-white overflow-x-auto">
                      {JSON.stringify(result.metadata, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Empty State */}
          {!result && !error && !testing && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              <Play className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Enter a query above and click &quot;Run Query&quot; to test the file store</p>
            </div>
          )}
        </div>

        {/* Footer */}
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
