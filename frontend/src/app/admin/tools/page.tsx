"use client";

import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
  Cloud,
  Database,
  Upload,
  Play,
  Shield,
} from "lucide-react";
import { AVAILABLE_ICONS } from "@/components/IconPicker";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import CreateFileStoreModal from "@/components/CreateFileStoreModal";
import FileStoreDetailModal from "@/components/FileStoreDetailModal";
import TestFileStoreModal from "@/components/TestFileStoreModal";
import { getApiBaseUrl } from "@/lib/api";
import { useTeam } from "@/lib/team-context";
import { UI_COPY } from "@/lib/ui-copy";

interface Tool {
  id: number;
  name: string;
  type: string;
  config: string | null;
  icon: string;
  created_at: string;
  visibility?: string;
  owner_team_agent_id?: number | null;
  owner_team_name?: string | null;
  created_by_username?: string | null;
  agent_usage_count?: number;
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

const getDocumentLibraryDisplayName = (tool: Tool, config: Record<string, unknown>) => {
  const normalizeDisplayName = (raw: string) =>
    raw
      .replace(/_search$/i, "")
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((part) => {
        if (/^[a-z]{2,4}$/i.test(part)) return part.toUpperCase();
        return part.charAt(0).toUpperCase() + part.slice(1);
      })
      .join(" ");

  const description =
    typeof config.description === "string" ? config.description.trim() : "";
  const descriptionMatch = description.match(/^search documents in\s+(.+)$/i);
  if (descriptionMatch?.[1]) {
    return normalizeDisplayName(descriptionMatch[1].trim());
  }

  const configuredName = [
    config.display_name,
    config.file_store_display_name,
    config.file_store_name,
  ].find((value) => typeof value === "string" && value.trim().length > 0) as string | undefined;

  if (configuredName) return normalizeDisplayName(configuredName.trim());

  return normalizeDisplayName(tool.name || "");
};

function ToolsPageInner() {
  const apiBaseUrl = getApiBaseUrl();
  const { selectedTeamId, setSelectedTeamId } = useTeam();
  const searchParams = useSearchParams();
  const routeTeamId = searchParams.get("team_agent_id")
    ? parseInt(searchParams.get("team_agent_id") as string)
    : null;
  const sourceAgentId = searchParams.get("source_agent_id")
    ? parseInt(searchParams.get("source_agent_id") as string)
    : null;
  const returnAgentId = searchParams.get("return_agent_id");
  const returnTeamId = searchParams.get("return_team_id");
  const returnTeamName = searchParams.get("return_team_name");
  const draftId = searchParams.get("draft_id");
  const effectiveTeamId = routeTeamId ?? selectedTeamId;
  const agentReturnQuery = [
    effectiveTeamId ? `team_agent_id=${effectiveTeamId}` : "",
    returnTeamId ? `return_team_id=${returnTeamId}` : "",
    returnTeamName ? `return_team_name=${encodeURIComponent(returnTeamName)}` : "",
    draftId ? `draft_id=${draftId}` : "",
  ].filter(Boolean).join("&");
  const agentReturnHref = returnAgentId
    ? `/admin/agents/${returnAgentId}${agentReturnQuery ? `?${agentReturnQuery}` : ""}`
    : "/admin/teams";
  const newToolQuery = [
    effectiveTeamId ? `team_agent_id=${effectiveTeamId}` : "",
    sourceAgentId ? `source_agent_id=${sourceAgentId}` : "",
    returnAgentId ? `return_agent_id=${returnAgentId}` : "",
    returnTeamId ? `return_team_id=${returnTeamId}` : "",
    returnTeamName ? `return_team_name=${encodeURIComponent(returnTeamName)}` : "",
    draftId ? `draft_id=${draftId}` : "",
  ].filter(Boolean).join("&");

  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [showFileStoreModal, setShowFileStoreModal] = useState(false);
  const [selectedFileStore, setSelectedFileStore] = useState<any>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);

  useEffect(() => {
    if (routeTeamId && routeTeamId !== selectedTeamId) {
      setSelectedTeamId(routeTeamId);
    }
    fetchTools();
  }, [effectiveTeamId]);

  const fetchTools = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/tools${params}`, {
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
      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(
        `${apiBaseUrl}/api/admin/tools/${id}${params}`,
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
  const fileStoreTools = tools.filter((t) => t.type === "gemini_file_search");
  const customTools = tools.filter((t) => t.type === "custom_api" || t.type === "mcp_streamable_http");

  const handleManageFiles = async (tool: Tool) => {
    try {
      const config = tool.config ? JSON.parse(tool.config) : {};
      const geminiStoreId = config.gemini_store_id;

      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/file-stores?gemini_id=${geminiStoreId}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (!response.ok) throw new Error("Failed to fetch file store");

      const stores = await response.json();
      const store = stores.find((s: any) => s.gemini_store_id === geminiStoreId);

      if (store) {
        setSelectedFileStore(store);
        setShowDetailModal(true);
      }
    } catch (error) {
      console.error("Failed to fetch file store:", error);
      alert("Failed to open file store details");
    }
  };

  const handleTestStore = async (tool: Tool) => {
    try {
      const config = tool.config ? JSON.parse(tool.config) : {};
      const geminiStoreId = config.gemini_store_id;

      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/file-stores?gemini_id=${geminiStoreId}`,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      if (!response.ok) throw new Error("Failed to fetch file store");

      const stores = await response.json();
      const store = stores.find((s: any) => s.gemini_store_id === geminiStoreId);

      if (store) {
        setSelectedFileStore(store);
        setShowTestModal(true);
      }
    } catch (error) {
      console.error("Failed to fetch file store:", error);
      alert("Failed to open file store test");
    }
  };

  if (loading) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading tools...</div>
    );
  }

  return (
    <div className="space-y-6">
      <WorkflowNavigator
        backLabel={returnAgentId ? "Back to Agent" : "Team Agents"}
        backHref={agentReturnHref}
        steps={[
          { label: returnAgentId ? "Agent Editor" : "Team Agents", href: agentReturnHref },
          { label: UI_COPY.tools.navLabel, active: true },
        ]}
        actions={[
          { label: UI_COPY.tools.actions.addIntegration, href: `/admin/tools/new${newToolQuery ? `?${newToolQuery}` : ""}`, variant: "primary" },
          { label: "Channels", href: "/admin/tools/channels", variant: "outline" },
        ]}
      />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            {UI_COPY.tools.pageTitle}
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {UI_COPY.tools.pageSubtitle}
          </p>
        </div>
        <Link
          href={`/admin/tools/new${newToolQuery ? `?${newToolQuery}` : ""}`}
          className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          <Plus className="w-4 h-4" />
          {UI_COPY.tools.actions.addIntegration}
        </Link>
      </div>

      {/* Built-in Tools */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
          {UI_COPY.tools.sections.readyToUse}
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
                          {UI_COPY.tools.builtInNames[tool.name] || tool.name}
                        </h3>
                        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          {UI_COPY.tools.builtInDescriptions[tool.name] || config.description || "Included capability"}
                        </p>
                        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                          {UI_COPY.tools.meta.ownedBy}: {tool.owner_team_name || "N/A"} | {UI_COPY.tools.meta.createdBy}: {tool.created_by_username || "N/A"} | {UI_COPY.tools.meta.usedByAgents} {tool.agent_usage_count ?? 0} {UI_COPY.tools.meta.agents}
                        </p>
                      </div>
                    </div>
                    <span className="px-3 py-1 text-xs font-semibold rounded-full bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-300">
                      {UI_COPY.tools.badges.included}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* File Store Tools */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {UI_COPY.tools.sections.documentSearch}
          </h2>
          <button
            onClick={() => setShowFileStoreModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500"
          >
            <Plus className="w-4 h-4" />
            {UI_COPY.tools.actions.addDocumentLibrary}
          </button>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          {fileStoreTools.length === 0 ? (
            <div className="p-8 text-center">
              <Database className="mx-auto h-12 w-12 text-gray-400 mb-3" />
              <p className="text-gray-600 dark:text-gray-400 mb-4">
                {UI_COPY.tools.empty.documentLibraries}
              </p>
              <button
                onClick={() => setShowFileStoreModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-amber-600 hover:bg-amber-700"
              >
                <Plus className="w-4 h-4" />
                {UI_COPY.tools.actions.addDocumentLibrary}
              </button>
            </div>
          ) : (
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {fileStoreTools.map((tool) => {
                const config = tool.config ? JSON.parse(tool.config) : {};
                return (
                  <div
                    key={tool.id}
                    className="p-4 flex items-start gap-4 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
                  >
                    {/* Icon */}
                    <div className="flex-shrink-0 w-10 h-10 bg-amber-100 dark:bg-amber-900 rounded-lg flex items-center justify-center">
                      <Database className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-base font-medium text-gray-900 dark:text-white truncate">
                          {(() => {
                            const description =
                              typeof config.description === "string" ? config.description.trim() : "";
                            const descriptionMatch = description.match(/^search documents in\s+(.+)$/i);
                            if (descriptionMatch?.[1]) return descriptionMatch[1].trim();
                            return getDocumentLibraryDisplayName(tool, config);
                          })()}
                        </h3>
                        <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-300 text-xs font-medium rounded">
                          {UI_COPY.tools.badges.documentSearch}
                        </span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                        {config.description || "Finds answers from your uploaded documents."}
                      </p>
                      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                        {UI_COPY.tools.meta.ownedBy}: {tool.owner_team_name || "N/A"} | {UI_COPY.tools.meta.createdBy}: {tool.created_by_username || "N/A"} | {UI_COPY.tools.meta.usedByAgents} {tool.agent_usage_count ?? 0} {UI_COPY.tools.meta.agents}
                      </p>
                    </div>

                    {/* Actions */}
                    <div className="flex-shrink-0 flex gap-2">
                      <button
                        onClick={() => handleManageFiles(tool)}
                        className="p-2 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
                        title="Manage documents"
                      >
                        <Upload className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                      </button>
                      <button
                        onClick={() => handleTestStore(tool)}
                        className="p-2 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
                        title="Test document search"
                      >
                        <Play className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                      </button>
                      <button
                        onClick={() => handleDelete(tool.id)}
                        className="p-2 hover:bg-red-100 dark:hover:bg-red-900 rounded-md transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4 text-red-600 dark:text-red-400" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Custom Tools */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
          {UI_COPY.tools.sections.externalIntegrations}
        </h2>
        {customTools.length === 0 ? (
          <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              {UI_COPY.tools.empty.externalIntegrations}
            </p>
            <Link
              href={`/admin/tools/new${newToolQuery ? `?${newToolQuery}` : ""}`}
              className="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
            >
              {UI_COPY.tools.actions.addIntegration}
            </Link>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 shadow overflow-hidden sm:rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="divide-y divide-gray-200 dark:divide-gray-700">
              {customTools.map((tool) => {
                const config = tool.config ? JSON.parse(tool.config) : {};
                const isOwned = effectiveTeamId && tool.owner_team_agent_id === effectiveTeamId;
                const isGlobal = tool.visibility === "global";
                const isSystem = tool.type === "builtin";
                const canEdit = !effectiveTeamId || isOwned || isSystem;
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
                            {/* Ownership badges */}
                            {effectiveTeamId && isOwned && (
                              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
                            Owned by this team
                              </span>
                            )}
                            {effectiveTeamId && isGlobal && !isOwned && (
                              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-orange-100 dark:bg-orange-900/20 text-orange-700 dark:text-orange-400">
                            Shared across teams
                              </span>
                            )}
                            {effectiveTeamId && !isOwned && !isGlobal && (
                              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
                            Owned by another team
                              </span>
                            )}
                          </div>
                          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                            {config.description || "External integration"}
                          </p>
                          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                            {UI_COPY.tools.meta.ownedBy}: {tool.owner_team_name || "N/A"} | {UI_COPY.tools.meta.createdBy}: {tool.created_by_username || "N/A"} | {UI_COPY.tools.meta.usedByAgents} {tool.agent_usage_count ?? 0} {UI_COPY.tools.meta.agents}
                          </p>
                          {config.endpoint && (
                            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 truncate">
                              {config.endpoint}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {canEdit ? (
                          <Link
                            href={`/admin/tools/${tool.id}?team_agent_id=${effectiveTeamId}`}
                            className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                            title="Edit integration"
                          >
                            <Pencil className="w-4 h-4" />
                          </Link>
                        ) : (
                          <span className="p-2 text-gray-300 dark:text-gray-600 cursor-not-allowed" title="Only the owning team can edit this tool">
                            <Pencil className="w-4 h-4" />
                          </span>
                        )}
                        {canEdit ? (
                          <button
                            onClick={() => handleDelete(tool.id)}
                            className="p-2 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            title="Delete integration"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        ) : (
                          <span className="p-2 text-gray-300 dark:text-gray-600 cursor-not-allowed" title="Only the owning team can delete this tool">
                            <Trash2 className="w-4 h-4" />
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* File Store Modals */}
      {showFileStoreModal && (
        <CreateFileStoreModal
          teamAgentId={effectiveTeamId}
          assignAgentId={sourceAgentId}
          onClose={() => {
            setShowFileStoreModal(false);
          }}
          onSuccess={() => {
            setShowFileStoreModal(false);
            fetchTools(); // Refresh tool list after creation
          }}
        />
      )}

      {showDetailModal && selectedFileStore && (
        <FileStoreDetailModal
          store={selectedFileStore}
          onClose={() => {
            setShowDetailModal(false);
            setSelectedFileStore(null);
          }}
        />
      )}

      {showTestModal && selectedFileStore && (
        <TestFileStoreModal
          store={selectedFileStore}
          onClose={() => {
            setShowTestModal(false);
            setSelectedFileStore(null);
          }}
        />
      )}
    </div>
  );
}

export default function ToolsPage() {
  return (
    <Suspense>
      <ToolsPageInner />
    </Suspense>
  );
}
