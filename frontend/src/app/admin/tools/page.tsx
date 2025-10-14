"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface Tool {
  id: number;
  name: string;
  type: string;
  config: string | null;
  created_at: string;
}

export default function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTools();
  }, []);

  const fetchTools = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch("http://localhost:8000/api/admin/tools", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error("Failed to fetch tools");

      const data = await response.json();
      setTools(data);
    } catch (error) {
      console.error("Failed to fetch tools:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this custom tool?")) return;

    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `http://localhost:8000/api/admin/tools/${id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Failed to delete tool");

      // Refresh tools list
      fetchTools();
    } catch (error) {
      console.error("Failed to delete tool:", error);
      alert("Failed to delete tool. Make sure it's a custom tool.");
    }
  };

  const builtinTools = tools.filter((t) => t.type === "builtin");
  const customTools = tools.filter((t) => t.type === "custom_api" || t.type === "mcp_streamable_http");

  if (loading) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading tools...</div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Tools
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Manage built-in, custom API, and MCP tools
          </p>
        </div>
        <Link
          href="/admin/tools/new"
          className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          + New Custom Tool
        </Link>
      </div>

      {/* Built-in Tools */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
          Built-in Tools
        </h2>
        <div className="bg-white dark:bg-gray-800 shadow overflow-hidden sm:rounded-lg border border-gray-200 dark:border-gray-700">
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {builtinTools.map((tool) => {
              const config = tool.config ? JSON.parse(tool.config) : {};
              return (
                <div key={tool.id} className="p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <h3 className="text-base font-medium text-gray-900 dark:text-white">
                        {tool.name}
                      </h3>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        {config.description || "Built-in system tool"}
                      </p>
                    </div>
                    <span className="px-3 py-1 text-xs font-semibold rounded-full bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-300">
                      Built-in
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Custom Tools */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
          Custom API & MCP Tools
        </h2>
        {customTools.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              No custom tools found. Create your first custom tool to integrate external APIs or MCP servers.
            </p>
            <Link
              href="/admin/tools/new"
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              Create Custom Tool
            </Link>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 shadow overflow-hidden sm:rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {customTools.map((tool) => {
                const config = tool.config ? JSON.parse(tool.config) : {};
                return (
                  <div key={tool.id} className="p-6">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3">
                          <h3 className="text-base font-medium text-gray-900 dark:text-white">
                            {tool.name}
                          </h3>
                          <span className={`px-3 py-1 text-xs font-semibold rounded-full ${
                            tool.type === "mcp_streamable_http"
                              ? "bg-purple-100 dark:bg-purple-900/20 text-purple-800 dark:text-purple-300"
                              : "bg-blue-100 dark:bg-blue-900/20 text-blue-800 dark:text-blue-300"
                          }`}>
                            {tool.type === "mcp_streamable_http" ? "MCP" : "Custom API"}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          {config.description || "Custom API tool"}
                        </p>
                        {config.endpoint && (
                          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                            Endpoint: {config.endpoint}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center space-x-2">
                        <Link
                          href={`/admin/tools/${tool.id}`}
                          className="text-blue-600 dark:text-blue-400 hover:text-blue-900 dark:hover:text-blue-300 text-sm font-medium"
                        >
                          Edit
                        </Link>
                        <button
                          onClick={() => handleDelete(tool.id)}
                          className="text-red-600 dark:text-red-400 hover:text-red-900 dark:hover:text-red-300 text-sm font-medium"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
