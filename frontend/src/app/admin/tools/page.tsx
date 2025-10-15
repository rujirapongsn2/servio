"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Wrench,
  Plus,
  Pencil,
  Trash2,
  ShoppingCart,
  RotateCcw,
  Globe,
  Info,
  Zap,
  Code,
  Cloud
} from "lucide-react";
import { AVAILABLE_ICONS } from "@/components/IconPicker";

interface Tool {
  id: number;
  name: string;
  type: string;
  config: string | null;
  icon: string;
  created_at: string;
}

// Helper function to get icon for tool
const getToolIcon = (toolName: string, toolType: string) => {
  const name = toolName.toLowerCase();

  // Built-in tools
  if (name.includes('order')) return ShoppingCart;
  if (name.includes('refund')) return RotateCcw;
  if (name.includes('search') || name.includes('web')) return Globe;
  if (name.includes('softnix') || name.includes('info')) return Info;

  // Custom/MCP tools
  if (toolType === 'mcp_streamable_http') return Cloud;
  if (toolType === 'custom_api') return Zap;

  // Default
  return Wrench;
};

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
          className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          <Plus className="w-4 h-4" />
          New Custom Tool
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
              // Use stored icon or fallback to helper function
              const IconComponent = AVAILABLE_ICONS[tool.icon] || getToolIcon(tool.name, tool.type);
              return (
                <div key={tool.id} className="p-6 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-1">
                      <div className="flex-shrink-0 w-10 h-10 bg-green-100 dark:bg-green-900/20 rounded-lg flex items-center justify-center">
                        <IconComponent className="w-5 h-5 text-green-600 dark:text-green-400" />
                      </div>
                      <div>
                        <h3 className="text-base font-medium text-gray-900 dark:text-white">
                          {tool.name}
                        </h3>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          {config.description || "Built-in system tool"}
                        </p>
                      </div>
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
                // Use stored icon or fallback to helper function
                const IconComponent = AVAILABLE_ICONS[tool.icon] || getToolIcon(tool.name, tool.type);
                return (
                  <div key={tool.id} className="p-6 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 flex-1">
                        <div className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${
                          tool.type === "mcp_streamable_http"
                            ? "bg-purple-100 dark:bg-purple-900/20"
                            : "bg-blue-100 dark:bg-blue-900/20"
                        }`}>
                          <IconComponent className={`w-5 h-5 ${
                            tool.type === "mcp_streamable_http"
                              ? "text-purple-600 dark:text-purple-400"
                              : "text-blue-600 dark:text-blue-400"
                          }`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="text-base font-medium text-gray-900 dark:text-white">
                              {tool.name}
                            </h3>
                            <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
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
                            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 truncate">
                              {config.endpoint}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/admin/tools/${tool.id}`}
                          className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                          title="Edit Tool"
                        >
                          <Pencil className="w-4 h-4" />
                        </Link>
                        <button
                          onClick={() => handleDelete(tool.id)}
                          className="p-2 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-md transition-colors"
                          title="Delete Tool"
                        >
                          <Trash2 className="w-4 h-4" />
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
