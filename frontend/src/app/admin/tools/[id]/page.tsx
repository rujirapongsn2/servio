"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { IconPicker } from "@/components/IconPicker";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import { getApiBaseUrl } from "@/lib/api";
import { useTeam } from "@/lib/team-context";
import CustomApiRequestEditor from "@/components/CustomApiRequestEditor";
import { requestDraft, serializeRequest } from "@/lib/custom-api";
import { UI_COPY } from "@/lib/ui-copy";

function EditToolForm() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const toolId = params.id as string;
  const apiBaseUrl = getApiBaseUrl();
  const { selectedTeamId, setSelectedTeamId } = useTeam();
  const routeTeamId = searchParams.get("team_agent_id")
    ? parseInt(searchParams.get("team_agent_id") as string)
    : null;
  const effectiveTeamId = routeTeamId ?? selectedTeamId;

  const [loading, setLoading] = useState(true);
  const [toolType, setToolType] = useState<"custom_api" | "mcp_streamable_http">("custom_api");
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    endpoint: "",
    method: "POST",
    auth_token: "",
    transport: "streamable_http",
    mcp_tools: "",
    timeout_seconds: "60",
    auth_mode: "bearer", // bearer | query | header
    auth_param_name: "apikey",
    auth_header_name: "X-API-Key",
    icon: "Wrench",
    visibility: "team",
  });
  const [customRequest, setCustomRequest] = useState(() => requestDraft());
  const [originalConfig, setOriginalConfig] = useState<Record<string, unknown>>({});
  const [requestChanged, setRequestChanged] = useState(false);
  const [requestLoadError, setRequestLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchTool();
  }, [toolId]);

  const fetchTool = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/tools/${toolId}${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch tool");
      }

      const tool = await response.json();
      const config = tool.config ? JSON.parse(tool.config) : {};

      setOriginalConfig(config);
      setRequestChanged(false);
      if (tool.type === "custom_api") {
        try { setCustomRequest(requestDraft(config)); setRequestLoadError(""); }
        catch { setRequestLoadError("Unsupported or invalid Custom API request. Update the configuration before editing."); }
      }
      setToolType(tool.type);
      setFormData({
        name: tool.name || "",
        description: config.description || "",
        endpoint: config.endpoint || "",
        method: config.method || "POST",
        auth_token: config.auth_token || "",
        transport: config.transport || "streamable_http",
        mcp_tools: config.tools ? config.tools.join(", ") : "",
        timeout_seconds: String(config.timeout_seconds || 60),
        auth_mode: config.auth_mode || "bearer",
        auth_param_name: config.auth_param_name || "apikey",
        auth_header_name: config.auth_header_name || "X-API-Key",
        icon: tool.icon || "Wrench",
        visibility: tool.visibility || "team",
      });
    } catch (err: any) {
      setError(err.message || "Failed to load tool");
    } finally {
      setLoading(false);
    }
  };

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
        timeout_seconds: parseInt(formData.timeout_seconds) || 60,
      };

      if (toolType === "custom_api") {
        if (requestLoadError) throw new Error(requestLoadError);
        config = { ...originalConfig };
        if (formData.description !== (originalConfig.description ?? "")) config.description = formData.description;
        if (requestChanged) {
          config = { ...config, endpoint: customRequest.endpoint, method: customRequest.method, auth_token: customRequest.auth_token, timeout_seconds: Number(customRequest.timeout_seconds), request: serializeRequest(customRequest) };
        }
      } else if (toolType === "mcp_streamable_http") {
        config.transport = formData.transport;
        config.auth_mode = formData.auth_mode;
        config.auth_param_name = formData.auth_param_name;
        config.auth_header_name = formData.auth_header_name;
        if (formData.mcp_tools.trim()) {
          config.tools = formData.mcp_tools.split(",").map(t => t.trim()).filter(t => t);
        } else {
          config.tools = [];
        }
        config.timeout_seconds = parseInt(formData.timeout_seconds) || 60;
      }

      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/tools/${toolId}${params}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: formData.name,
          config: config,
          icon: formData.icon,
          visibility: formData.visibility,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to update tool");
      }

      router.push("/admin/tools");
    } catch (err: any) {
      setError(err.message || "An error occurred while updating the tool");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-gray-600 dark:text-gray-400">Loading tool...</div>;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <WorkflowNavigator
        backLabel={UI_COPY.tools.navLabel}
        backHref="/admin/tools"
        steps={[
          { label: "Team Agents", href: "/admin/teams" },
          { label: UI_COPY.tools.navLabel, href: "/admin/tools" },
          { label: "Edit Integration", active: true },
        ]}
      />

      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Edit Integration
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Update how this external system is connected
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Integration Setup
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Integration Type
              </label>
              <select
                value={toolType}
                disabled
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed"
              >
                <option value="custom_api">Custom API</option>
                <option value="mcp_streamable_http">MCP Streamable HTTP</option>
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Integration type cannot be changed
              </p>
            </div>

            <div>
              <label htmlFor="integration-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Integration Name
              </label>
              <input id="integration-name"
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="e.g., order_status_lookup"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
            </div>

            <IconPicker
              selectedIcon={formData.icon}
              onIconSelect={(icon) => setFormData({ ...formData, icon })}
            />

            {effectiveTeamId && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Visibility
                </label>
                <select
                  value={formData.visibility}
                  onChange={(e) => setFormData({ ...formData, visibility: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                >
                  <option value="team">Private (this team only)</option>
                  <option value="global">Global (all teams can use)</option>
                </select>
              </div>
            )}

            <div>
              <label htmlFor="integration-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Description
              </label>
              <textarea id="integration-description"
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

            {toolType === "custom_api" ? (
              requestLoadError ? <p role="alert" className="text-sm text-red-600">{requestLoadError}</p> :
              <CustomApiRequestEditor value={customRequest} onChange={draft => { setCustomRequest(draft); setRequestChanged(true); }} />
            ) : <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                MCP Server Endpoint
              </label>
              <input
                type="url"
                required
                value={formData.endpoint}
                onChange={(e) =>
                  setFormData({ ...formData, endpoint: e.target.value })
                }
                placeholder="https://mcp-server.example.com/mcp"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              {toolType === "mcp_streamable_http" && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  MCP Streamable HTTP endpoint (usually ends with /mcp)
                </p>
              )}
            </div>

            {/* Timeout seconds for both tool types */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Timeout (seconds)
              </label>
              <input
                type="number"
                min={1}
                value={formData.timeout_seconds}
                onChange={(e) => setFormData({ ...formData, timeout_seconds: e.target.value })}
                placeholder="60"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Increase if your MCP/API takes longer to respond.
              </p>
            </div>

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

            {/* Auth configuration */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Authorization (Optional)
              </label>
              {toolType === "mcp_streamable_http" && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <select
                      value={formData.auth_mode}
                      onChange={(e) => setFormData({ ...formData, auth_mode: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                    >
                      <option value="bearer">Bearer token (Authorization)</option>
                      <option value="query">Query parameter</option>
                      <option value="header">Custom header</option>
                    </select>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Choose how to pass your MCP API key (e.g., AlphaVantage uses query param `apikey`).
                    </p>
                  </div>
                  {formData.auth_mode === "query" && (
                    <div>
                      <input
                        type="text"
                        value={formData.auth_param_name}
                        onChange={(e) => setFormData({ ...formData, auth_param_name: e.target.value })}
                        placeholder="Query param name (e.g., apikey)"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                      />
                    </div>
                  )}
                  {formData.auth_mode === "header" && (
                    <div>
                      <input
                        type="text"
                        value={formData.auth_header_name}
                        onChange={(e) => setFormData({ ...formData, auth_header_name: e.target.value })}
                        placeholder="Header name (e.g., X-API-Key)"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                      />
                    </div>
                  )}
                </div>
              )}
              {/* Token input used for all auth modes */}
              <input
                type="text"
                value={formData.auth_token}
                onChange={(e) =>
                  setFormData({ ...formData, auth_token: e.target.value })
                }
                placeholder={
                  formData.auth_mode === "query"
                    ? "Optional: Your API key value"
                    : formData.auth_mode === "header"
                    ? "Optional: Your API key value"
                    : "Optional: Your bearer token"
                }
                className="mt-3 w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Leave empty if the MCP server doesn't require authentication
              </p>
            </div>
            </>}
          </div>
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
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function EditToolPage() {
  return (
    <Suspense>
      <EditToolForm />
    </Suspense>
  );
}
