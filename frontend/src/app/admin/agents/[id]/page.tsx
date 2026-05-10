"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import { Sparkles, Wrench } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { useTeam } from "@/lib/team-context";

interface Tool {
  id: number;
  name: string;
  type: string;
}

interface Provider {
  id: number;
  name: string;
}

interface Agent {
  id?: number;
  name: string;
  model: string;
  instructions: string;
  is_starting_agent: boolean;
  tools: Tool[];
  handoffs: { id: number; name: string }[];
  llm_provider_id?: number | null;
  llm_provider?: Provider | null;
}

export default function AgentEditorPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const apiBaseUrl = getApiBaseUrl();
  const { selectedTeamId, setSelectedTeamId } = useTeam();
  const isNew = params.id === "new";
  const agentId = isNew ? null : parseInt(params.id as string);
  const routeTeamId = searchParams.get("team_agent_id")
    ? parseInt(searchParams.get("team_agent_id") as string)
    : null;
  const returnTeamId = searchParams.get("return_team_id")
    ? parseInt(searchParams.get("return_team_id") as string)
    : null;
  const returnTeamName = searchParams.get("return_team_name");
  const effectiveTeamId = routeTeamId ?? selectedTeamId;
  const teamManageHref = returnTeamId ? `/admin/teams?manage_team=${returnTeamId}` : "/admin/teams";
  const autoSelectToolId = searchParams.get("auto_select_tool_id")
    ? parseInt(searchParams.get("auto_select_tool_id") as string)
    : null;

  const [formData, setFormData] = useState<Agent>({
    name: "",
    model: "",
    instructions: "",
    is_starting_agent: false,
    tools: [],
    handoffs: [],
    llm_provider_id: undefined,
  });

  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [availableAgents, setAvailableAgents] = useState<
    { id: number; name: string }[]
  >([]);
  const [availableProviders, setAvailableProviders] = useState<Provider[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (routeTeamId) {
      setSelectedTeamId(routeTeamId);
    }
    fetchTools();
    fetchAgents();
    fetchProviders();
    if (!isNew && agentId) {
      fetchAgent();
    }
  }, [effectiveTeamId]);

  const fetchProviders = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}/api/admin/llm-providers`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setAvailableProviders(data);
    } catch (error) {
      console.error("Failed to fetch providers:", error);
    }
  };

  const fetchModels = async (providerId: number) => {
    setFetchingModels(true);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}/api/admin/llm-providers/${providerId}/models`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      // Expecting list of objects with 'id' field, or just strings?
      // provider_service returns model objects. OpenAIChatCompletionsModel expects string ID.
      // Usually OpenAI models list has 'id' field.
      const modelIds = data.map((m: any) => m.id || m);
      setAvailableModels(modelIds);
    } catch (error) {
      console.error("Failed to fetch models:", error);
      // Fallback or keep empty
      setAvailableModels([]);
    } finally {
      setFetchingModels(false);
    }
  };

  const fetchTools = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/tools${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setAvailableTools(data);
      setFormData((prev) => {
        let tools = prev.tools;
        const dateTimeTool = data.find((tool: Tool) => tool.name === "DateTimeTool");
        if (dateTimeTool && !tools.some((t) => t.id === dateTimeTool.id)) {
          tools = [...tools, dateTimeTool];
        }
        if (autoSelectToolId) {
          const autoTool = data.find((tool: Tool) => tool.id === autoSelectToolId);
          if (autoTool && !tools.some((t) => t.id === autoTool.id)) {
            tools = [...tools, autoTool];
          }
        }
        if (tools === prev.tools) return prev;
        return { ...prev, tools };
      });
    } catch (error) {
      console.error("Failed to fetch tools:", error);
    }
  };

  const fetchAgents = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const query = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/agents${query}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setAvailableAgents(
        data.filter((a: any) => a.id !== agentId).map((a: any) => ({ id: a.id, name: a.name }))
      );
    } catch (error) {
      console.error("Failed to fetch agents:", error);
    }
  };

  const fetchAgent = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const query = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(
        `${apiBaseUrl}/api/admin/agents/${agentId}${query}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await response.json();

      // Extract provider ID from nested object if present
      const providerId = data.llm_provider?.id || null;

      setFormData({
        ...data,
        llm_provider_id: providerId
      });

      // Load models if provider is set
      if (providerId) {
        fetchModels(providerId);
      } else {
        // Default OpenAI models
        setAvailableModels(["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]);
      }
    } catch (error) {
      console.error("Failed to fetch agent:", error);
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
      const payload = {
        ...(availableTools.find((tool) => tool.name === "DateTimeTool")
          ? {
              tool_ids: Array.from(
                new Set([
                  ...formData.tools.map((t) => t.id),
                  availableTools.find((tool) => tool.name === "DateTimeTool")!.id,
                ])
              ),
            }
          : {
              tool_ids: formData.tools.map((t) => t.id),
            }),
        name: formData.name,
        model: formData.model,
        instructions: formData.instructions,
        handoff_agent_ids: formData.handoffs.map((h) => h.id),
        is_starting_agent: formData.is_starting_agent,
        llm_provider_id: formData.llm_provider_id,
      };

      const query = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const url = isNew
        ? `${apiBaseUrl}/api/admin/agents`
        : `${apiBaseUrl}/api/admin/agents/${agentId}`;

      const response = await fetch(`${url}${query}`, {
        method: isNew ? "POST" : "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to save agent");
      }

      const result = await response.json();
      if (isNew && returnTeamId) {
        const idMatch = result.message?.match(/ID\s+(\d+)/);
        const createdAgentId = idMatch ? parseInt(idMatch[1]) : null;
        if (createdAgentId) {
          const teamRes = await fetch(`${apiBaseUrl}/api/admin/team-agents/${returnTeamId}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (teamRes.ok) {
            const team = await teamRes.json();
            const existingMembers = team.members || [];
            const memberIds = Array.from(new Set([
              ...existingMembers.map((member: any) => member.agent_id),
              createdAgentId,
            ]));
            const currentStarting = existingMembers.find((member: any) => member.role === "starting")?.agent_id;
            const startingAgentId = formData.is_starting_agent || !currentStarting
              ? createdAgentId
              : currentStarting;
            await fetch(`${apiBaseUrl}/api/admin/team-agents/${returnTeamId}/members`, {
              method: "PUT",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({
                member_agent_ids: memberIds,
                starting_agent_id: startingAgentId,
              }),
            });
          }
        }
      }

      router.push(teamManageHref);
    } catch (err: any) {
      setError(err.message || "An error occurred while saving");
    } finally {
      setSaving(false);
    }
  };

  const toggleTool = (tool: Tool) => {
    if (tool.name === "DateTimeTool") {
      return;
    }
    if (formData.tools.some((t) => t.id === tool.id)) {
      setFormData({
        ...formData,
        tools: formData.tools.filter((t) => t.id !== tool.id),
      });
    } else {
      setFormData({
        ...formData,
        tools: [...formData.tools, tool],
      });
    }
  };

  const toggleHandoff = (agent: { id: number; name: string }) => {
    if (formData.handoffs.some((h) => h.id === agent.id)) {
      setFormData({
        ...formData,
        handoffs: formData.handoffs.filter((h) => h.id !== agent.id),
      });
    } else {
      setFormData({
        ...formData,
        handoffs: [...formData.handoffs, agent],
      });
    }
  };

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    const providerId = (value === "default" || value === "") ? null : parseInt(value);

    // Explicitly set undefined if it's the placeholder "Select Provider"
    const finalProviderId = value === "" ? undefined : providerId;

    setFormData({
      ...formData,
      llm_provider_id: finalProviderId,
      model: "", // Reset model when provider changes
    });

    if (providerId) {
      fetchModels(providerId);
    } else if (value === "default") {
      setAvailableModels(["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]);
    } else {
      setAvailableModels([]);
    }
  };

  const handleOptimizePrompt = async () => {
    if (!formData.instructions.trim()) {
      alert("Please enter some instructions first");
      return;
    }

    setOptimizing(true);
    setError("");

    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/agents/optimize-prompt`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            instructions: formData.instructions,
            agent_name: formData.name,
            model: formData.model,
            llm_provider_id: formData.llm_provider_id,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to optimize prompt");
      }

      const data = await response.json();
      setFormData({
        ...formData,
        instructions: data.optimized_instructions,
      });
    } catch (err: any) {
      setError(err.message || "Failed to optimize prompt");
    } finally {
      setOptimizing(false);
    }
  };

  if (loading) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading agent...</div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <WorkflowNavigator
        backLabel={returnTeamId ? "Team Manage" : "Team Agents"}
        backHref={teamManageHref}
        steps={[
          { label: "Team Agents", href: returnTeamId ? `/admin/teams?manage_team=${returnTeamId}` : "/admin/teams" },
          ...(returnTeamId
            ? [{ label: returnTeamName || "Manage Team", href: teamManageHref }]
            : []),
          { label: isNew ? "Create Agent" : "Edit Agent", active: true },
        ]}
        actions={[
          { label: "Tools", href: `/admin/tools?team_agent_id=${effectiveTeamId}`, variant: "outline" },
          { label: "Providers", href: "/admin/providers", variant: "outline" },
        ]}
      />

      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          {isNew ? "Create New Agent" : `Edit Agent: ${formData.name}`}
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Configure the agent's behavior, tools, and handoffs
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Basic Information
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Agent Name
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                LLM Provider <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.llm_provider_id === undefined ? "" : (formData.llm_provider_id === null ? "default" : formData.llm_provider_id)}
                onChange={handleProviderChange}
                required
                className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white ${formData.llm_provider_id === undefined ? "border-red-300 dark:border-red-900" : "border-gray-300 dark:border-gray-700"
                  }`}
              >
                <option value="" disabled>-- Please Select LLM Provider --</option>
                <option value="default">Default (OpenAI)</option>
                {availableProviders.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {formData.llm_provider_id === undefined && (
                <p className="mt-1 text-xs text-red-500">
                  Please select an LLM provider to continue
                </p>
              )}
              {availableProviders.length === 0 && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Tip: You can add more providers in the{" "}
                  <a href="/admin/llm-providers" className="underline font-medium">
                    LLM Providers
                  </a>{" "}
                  settings.
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Model {fetchingModels && <span className="text-xs text-gray-400 ml-2">(Loading...)</span>}
              </label>
              <select
                value={formData.model}
                onChange={(e) =>
                  setFormData({ ...formData, model: e.target.value })
                }
                disabled={fetchingModels || formData.llm_provider_id === undefined}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white disabled:opacity-50"
                required
              >
                {formData.llm_provider_id === undefined ? (
                  <option value="">-- Select Provider First --</option>
                ) : (
                  <option value="" disabled>-- Select Model --</option>
                )}
                {availableModels.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
                {!availableModels.includes(formData.model) && formData.model && (
                  <option value={formData.model}>{formData.model} (Current)</option>
                )}
              </select>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Instructions
                </label>
                <button
                  type="button"
                  onClick={handleOptimizePrompt}
                  disabled={optimizing || !formData.instructions.trim()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md text-purple-700 dark:text-purple-300 bg-purple-100 dark:bg-purple-900/20 hover:bg-purple-200 dark:hover:bg-purple-900/30 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="Use AI to optimize and improve your instructions"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  {optimizing ? "Optimizing..." : "Optimize with AI"}
                </button>
              </div>
              <textarea
                required
                rows={6}
                value={formData.instructions}
                onChange={(e) =>
                  setFormData({ ...formData, instructions: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                placeholder="Describe the agent's purpose and behavior..."
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Use the "Optimize with AI" button to automatically improve your instructions using AI
              </p>
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                id="is_starting_agent"
                checked={formData.is_starting_agent}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    is_starting_agent: e.target.checked,
                  })
                }
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <label
                htmlFor="is_starting_agent"
                className="ml-2 block text-sm text-gray-700 dark:text-gray-300"
              >
                Set as starting agent (first agent users interact with)
              </label>
            </div>
          </div>
        </div>

        {/* Tools */}
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Tools
            </h2>
            <Link
              href={`/admin/tools?team_agent_id=${effectiveTeamId}${agentId ? `&source_agent_id=${agentId}` : ""}&return_agent_id=${params.id}&return_team_id=${returnTeamId ?? ""}&return_team_name=${encodeURIComponent(returnTeamName || "")}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/20 hover:bg-blue-200 dark:hover:bg-blue-900/30 transition-colors"
            >
              <Wrench className="w-3.5 h-3.5" />
              Manage Tools
            </Link>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select the tools this agent can use
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {availableTools.map((tool) => (
              <label
                key={tool.id}
                className="flex items-center space-x-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <input
                  type="checkbox"
                  checked={formData.tools.some((t) => t.id === tool.id)}
                  onChange={() => toggleTool(tool)}
                  disabled={tool.name === "DateTimeTool"}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    {tool.name}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {tool.type}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Handoffs */}
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Handoffs
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select agents this agent can transfer conversations to
          </p>
          {availableAgents.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No other agents available for handoffs
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {availableAgents.map((agent) => (
                <label
                  key={agent.id}
                  className="flex items-center space-x-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={formData.handoffs.some((h) => h.id === agent.id)}
                    onChange={() => toggleHandoff(agent)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    {agent.name}
                  </div>
                </label>
              ))}
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
            onClick={() => router.push(teamManageHref)}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {saving ? "Saving..." : isNew ? "Create Agent" : "Save Changes"}
          </button>
        </div>
      </form>
    </div>
  );
}
