"use client";

import { useRef, useState } from "react";
import { IconPicker } from "@/components/IconPicker";
import { getApiBaseUrl } from "@/lib/api";
import CustomApiRequestEditor from "@/components/CustomApiRequestEditor";
import { requestDraft, serializeRequest, validateEndpoint } from "@/lib/custom-api";
import { parseCreatedTool, toolCreationRequest, type CreatedTool, type ToolCreationContext } from "@/lib/tool-creation";

export interface CreateToolFormProps {
  context: ToolCreationContext;
  onCreated: (result: CreatedTool) => void;
  onCancel: () => void;
  onBusyChange?: (busy: boolean) => void;
}

export default function CreateToolForm({ context, onCreated, onCancel, onBusyChange }: CreateToolFormProps) {
  const apiBaseUrl = getApiBaseUrl();
  const attempt = useRef<{ payload: string; requestId: string } | null>(null);
  const inFlight = useRef(false);
  const [toolType, setToolType] = useState<"custom_api" | "mcp_streamable_http">("custom_api");
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    endpoint: "",
    auth_token: "",
    transport: "streamable_http",
    mcp_tools: "",
    timeout_seconds: "60",
    auth_mode: "bearer",
    auth_param_name: "apikey",
    auth_header_name: "X-API-Key",
    icon: "Wrench",
    visibility: "team",
  });
  const [customRequest, setCustomRequest] = useState(() => requestDraft());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (inFlight.current) return;
    setError("");
    try {
      let config;
      if (toolType === "custom_api") {
        config = { type: toolType, description: formData.description, endpoint: customRequest.endpoint, method: customRequest.method, auth_token: customRequest.auth_token, timeout_seconds: Number(customRequest.timeout_seconds), request: serializeRequest(customRequest) };
      } else {
        validateEndpoint(formData.endpoint);
        const timeout = Number(formData.timeout_seconds);
        if (!Number.isFinite(timeout) || timeout <= 0) throw new Error("Timeout must be greater than zero.");
        config = { type: toolType, description: formData.description, endpoint: formData.endpoint, auth_token: formData.auth_token, timeout_seconds: timeout, transport: formData.transport, auth_mode: formData.auth_mode, auth_param_name: formData.auth_param_name, auth_header_name: formData.auth_header_name, tools: formData.mcp_tools.split(",").map(name => name.trim()).filter(Boolean) };
      }
      const payload = { name: formData.name.trim(), config, icon: formData.icon, visibility: formData.visibility };
      const serialized = JSON.stringify({ context, payload });
      if (attempt.current?.payload !== serialized) attempt.current = { payload: serialized, requestId: crypto.randomUUID() };
      const request = toolCreationRequest(context, payload, attempt.current.requestId);
      inFlight.current = true;
      setSaving(true);
      onBusyChange?.(true);
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}${request.path}`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(request.body),
      });
      const data: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const detail = data && typeof data === "object" && "detail" in data && typeof data.detail === "string" ? data.detail : "Failed to create tool";
        throw new Error(detail);
      }
      const toolId = parseCreatedTool(data);
      onCreated({ tool_id: toolId, name: payload.name, type: toolType });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Failed to create tool");
    } finally {
      inFlight.current = false;
      setSaving(false);
      onBusyChange?.(false);
    }
  };

  return (
      <form onSubmit={handleSubmit} className="space-y-6">
        <fieldset disabled={saving} className="min-w-0 space-y-6">
        <div className="bg-white dark:bg-gray-800 shadow rounded-xl border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Integration Setup
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Integration Type
              </label>
              <select
                aria-label="Integration Type"
                value={toolType}
                onChange={(e) => { if (e.target.value === "custom_api" || e.target.value === "mcp_streamable_http") setToolType(e.target.value); }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              >
                <option value="custom_api">Custom API</option>
                <option value="mcp_streamable_http">MCP Streamable HTTP</option>
              </select>

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

            {context.kind === "tools-page" && context.teamId && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Visibility
                </label>
                <select
                  aria-label="Visibility"
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
              <CustomApiRequestEditor value={customRequest} onChange={setCustomRequest} />
            ) : <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                MCP Server Endpoint
              </label>
              <input
                type="url"
                required
                aria-label="MCP Server Endpoint"
                value={formData.endpoint}
                onChange={(e) =>
                  setFormData({ ...formData, endpoint: e.target.value })
                }
                placeholder="https://mcp-server.example.com/mcp"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />

            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Timeout (seconds)
              </label>
              <input
                type="number"
                min={1}
                aria-label="Timeout (seconds)"
                value={formData.timeout_seconds}
                onChange={(e) => setFormData({ ...formData, timeout_seconds: e.target.value })}
                placeholder="60"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
            </div>

            {toolType === "mcp_streamable_http" && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  MCP Tool Names (Optional)
                </label>
                <input
                  type="text"
                  aria-label="MCP Tool Names"
                value={formData.mcp_tools}
                  onChange={(e) =>
                    setFormData({ ...formData, mcp_tools: e.target.value })
                  }
                  placeholder="tool1, tool2, tool3"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Authorization (Optional)
              </label>
              {toolType === "mcp_streamable_http" && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <select
                      aria-label="Authorization mode"
                      value={formData.auth_mode}
                      onChange={(e) => setFormData({ ...formData, auth_mode: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                    >
                      <option value="bearer">Bearer token (Authorization)</option>
                      <option value="query">Query parameter</option>
                      <option value="header">Custom header</option>
                    </select>
                  </div>
                  {formData.auth_mode === "query" && (
                    <div>
                      <input
                        type="text"
                        aria-label="Query parameter name"
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
                        aria-label="Header name"
                value={formData.auth_header_name}
                        onChange={(e) => setFormData({ ...formData, auth_header_name: e.target.value })}
                        placeholder="Header name (e.g., X-API-Key)"
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                      />
                    </div>
                  )}
                </div>
              )}
              <input
                type="password"
                autoComplete="off"
                aria-label="Authorization token"
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
            </div>
            </>}
          </div>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
            <div role="alert" className="text-sm text-red-800 dark:text-red-300">{error}</div>
          </div>
        )}

        <div className="flex justify-end space-x-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {saving ? "Creating..." : "Add Integration"}
          </button>
        </div>
        </fieldset>
      </form>
  );
}
