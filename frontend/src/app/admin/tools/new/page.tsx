"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function NewToolPage() {
  const router = useRouter();
  const [toolType, setToolType] = useState<"custom_api" | "mcp_streamable_http">("custom_api");
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    endpoint: "",
    method: "POST",
    auth_token: "",
    transport: "streamable_http",
    mcp_tools: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);

    try {
      const token = localStorage.getItem("adminToken");

      let config: any = {
        type: toolType,
        description: formData.description,
        endpoint: formData.endpoint,
        auth_token: formData.auth_token,
      };

      if (toolType === "custom_api") {
        config.method = formData.method;
        config.payload_template = {
          query: "",
          inputs: {},
          files: [],
          citation: true,
          response_mode: "blocking",
        };
      } else if (toolType === "mcp_streamable_http") {
        config.transport = formData.transport;
        // Parse comma-separated tool names
        if (formData.mcp_tools.trim()) {
          config.tools = formData.mcp_tools.split(",").map(t => t.trim()).filter(t => t);
        } else {
          config.tools = [];
        }
      }

      const response = await fetch("http://localhost:8000/api/admin/tools", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: formData.name,
          config: config,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to create tool");
      }

      router.push("/admin/tools");
    } catch (err: any) {
      setError(err.message || "An error occurred while creating the tool");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Create Custom Tool
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Integrate an external API as a tool that agents can use
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Tool Configuration
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Tool Type
              </label>
              <select
                value={toolType}
                onChange={(e) => setToolType(e.target.value as "custom_api" | "mcp_streamable_http")}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              >
                <option value="custom_api">Custom API</option>
                <option value="mcp_streamable_http">MCP Streamable HTTP</option>
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {toolType === "custom_api"
                  ? "Direct API integration (REST, webhooks)"
                  : "Model Context Protocol server (standardized AI tool interface)"}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Tool Name
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="e.g., custom_search_tool"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Use lowercase with underscores (no spaces)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Description
              </label>
              <textarea
                required
                rows={3}
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="Describe what this tool does..."
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {toolType === "custom_api" ? "API Endpoint URL" : "MCP Server Endpoint"}
              </label>
              <input
                type="url"
                required
                value={formData.endpoint}
                onChange={(e) =>
                  setFormData({ ...formData, endpoint: e.target.value })
                }
                placeholder={toolType === "custom_api"
                  ? "https://api.example.com/endpoint"
                  : "https://mcp-server.example.com/mcp"}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              {toolType === "mcp_streamable_http" && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  MCP Streamable HTTP endpoint (usually ends with /mcp)
                </p>
              )}
            </div>

            {toolType === "custom_api" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  HTTP Method
                </label>
                <select
                  value={formData.method}
                  onChange={(e) =>
                    setFormData({ ...formData, method: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                >
                  <option value="POST">POST</option>
                  <option value="GET">GET</option>
                </select>
              </div>
            )}

            {toolType === "mcp_streamable_http" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  MCP Tool Names (Optional)
                </label>
                <input
                  type="text"
                  value={formData.mcp_tools}
                  onChange={(e) =>
                    setFormData({ ...formData, mcp_tools: e.target.value })
                  }
                  placeholder="tool1, tool2, tool3"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Comma-separated list of specific MCP tools to use. Leave empty to auto-discover all tools.
                </p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Authorization Token (Bearer)
              </label>
              <input
                type="text"
                value={formData.auth_token}
                onChange={(e) =>
                  setFormData({ ...formData, auth_token: e.target.value })
                }
                placeholder="Optional: Your API bearer token"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Leave empty if the {toolType === "custom_api" ? "API" : "MCP server"} doesn't require authentication
              </p>
            </div>
          </div>
        </div>

        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <h3 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">
            {toolType === "custom_api" ? "Example: Custom API Tool" : "Example: MCP Tool"}
          </h3>
          {toolType === "custom_api" ? (
            <div className="text-xs text-blue-800 dark:text-blue-400 space-y-1">
              <p>• Name: get_custom_info</p>
              <p>• Endpoint: https://genai.softnix.ai/external/api/chat-messages</p>
              <p>• Method: POST</p>
              <p>• Auth Token: Your Softnix API key</p>
            </div>
          ) : (
            <div className="text-xs text-blue-800 dark:text-blue-400 space-y-1">
              <p>• Name: mcp_weather_tool</p>
              <p>• Endpoint: https://mcp-server.example.com/mcp</p>
              <p>• MCP Tool Names: get_weather, get_forecast (optional)</p>
              <p>• Auth Token: Your MCP server API key (if required)</p>
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
            <div className="text-sm text-red-800 dark:text-red-300">{error}</div>
          </div>
        )}

        <div className="flex justify-end space-x-3">
          <button
            type="button"
            onClick={() => router.push("/admin/tools")}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {saving ? "Creating..." : "Create Tool"}
          </button>
        </div>
      </form>
    </div>
  );
}
