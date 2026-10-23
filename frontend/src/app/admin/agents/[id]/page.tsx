"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import { Sparkles, Wrench } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";
import { useTeam } from "@/lib/team-context";
import { DEFAULT_MODELS, parseModelIds } from "@/lib/provider-models";

interface Tool {
  id: number;
  name?: string | null;
  type?: string | null;
  config?: string | null;
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

interface AgentDraft {
  name: string;
  model: string;
  instructions: string;
  is_starting_agent: boolean;
  llm_provider_id?: number | null;
  tool_ids: number[];
  handoff_ids: number[];
}

const CUSTOM_MODEL = "__custom_model__";

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
  const routeDraftId = searchParams.get("draft_id");
  const effectiveTeamId = routeTeamId ?? selectedTeamId;
  const returnToWorkflow = (searchParams.get("return_to") === "workflow" || searchParams.get("return_workspace") === "workflow");
  const teamManageHref = returnTeamId
    ? returnToWorkflow ? `/admin/teams/${returnTeamId}/workflow` : `/admin/teams?manage_team=${returnTeamId}`
    : "/admin/teams";
  const autoSelectToolId = searchParams.get("auto_select_tool_id")
    ? parseInt(searchParams.get("auto_select_tool_id") as string)
    : null;
  const autoSelectProviderId = searchParams.get("select_provider_id")
    ? parseInt(searchParams.get("select_provider_id") as string)
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
  const [modelsError, setModelsError] = useState("");
  const [customModel, setCustomModel] = useState(false);
  const [toolsLoaded, setToolsLoaded] = useState(false);
  const [agentsLoaded, setAgentsLoaded] = useState(false);
  const [draftId, setDraftId] = useState<string | null>(routeDraftId);
  const [draftData, setDraftData] = useState<AgentDraft | null>(null);
  const [loadedDraftKey, setLoadedDraftKey] = useState<string | null>(null);
  const [hydratedDraftKey, setHydratedDraftKey] = useState<string | null>(null);
  const appliedProviderSelection = useRef<string | null>(null);
  const modelRequestId = useRef(0);

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [error, setError] = useState("");
  const draftStorageKey = draftId
    ? isNew
      ? `agent-draft:${draftId}`
      : `agent-draft:${effectiveTeamId ?? "global"}:${agentId}:${draftId}`
    : null;
  const draftReady = draftStorageKey !== null && loadedDraftKey === draftStorageKey;
  const draftHydrated = draftStorageKey !== null && hydratedDraftKey === draftStorageKey;
  const capabilitiesQuery = [
    effectiveTeamId ? `team_agent_id=${effectiveTeamId}` : "",
    agentId ? `source_agent_id=${agentId}` : "",
    `return_agent_id=${params.id}`,
    returnTeamId ? `return_team_id=${returnTeamId}` : "",
    returnTeamName ? `return_team_name=${encodeURIComponent(returnTeamName)}` : "",
    returnToWorkflow ? "return_workspace=workflow" : "",
    draftId ? `draft_id=${draftId}` : "",
  ].filter(Boolean).join("&");
  const providersQuery = [
    "return_to=agent_edit",
    `return_agent_id=${params.id}`,
    effectiveTeamId ? `team_agent_id=${effectiveTeamId}` : "",
    returnTeamId ? `return_team_id=${returnTeamId}` : "",
    returnTeamName ? `return_team_name=${encodeURIComponent(returnTeamName)}` : "",
    returnToWorkflow ? "return_workspace=workflow" : "",
    draftId ? `draft_id=${draftId}` : "",
  ].filter(Boolean).join("&");
  const providersHref = `/admin/providers${providersQuery ? `?${providersQuery}` : ""}`;
  const newProviderHref = `/admin/providers?${[
    "create=1",
    providersQuery,
  ].filter(Boolean).join("&")}`;
  const safeInstructions = typeof formData.instructions === "string" ? formData.instructions : "";

  const getCapabilityDisplayName = (tool: Tool): string => {
    if ((tool.type || "") === "gemini_file_search" || (tool.type || "") === "okf_knowledge_graph") {
      try {
        const parsedConfig =
          typeof tool.config === "string" ? JSON.parse(tool.config) : null;
        const displayName =
          parsedConfig?.display_name ||
          parsedConfig?.file_store_display_name ||
          parsedConfig?.file_store_name;
        if (typeof displayName === "string" && displayName.trim()) {
          return displayName.trim();
        }
      } catch {
        // Fall back to formatted tool name below.
      }
    }

    const rawName = typeof tool.name === "string" ? tool.name.trim() : "";
    if (!rawName) return "Unnamed Capability";
    const normalizedName = rawName.replace(/_search$/i, "");
    return normalizedName
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((part) => {
        const cleaned = part.trim();
        if (/^[a-z]{2,4}$/i.test(cleaned)) return cleaned.toUpperCase();
        return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
      })
      .join(" ");
  };

  const fetchModels = useCallback(async (providerId: number | null | undefined, currentModel = "") => {
    const requestId = ++modelRequestId.current;
    setModelsError("");
    setCustomModel(providerId === null && !!currentModel && !DEFAULT_MODELS.includes(currentModel));
    setAvailableModels(providerId === null ? DEFAULT_MODELS : []);
    setFetchingModels(typeof providerId === "number");
    if (typeof providerId !== "number") return;

    const token = localStorage.getItem("adminToken");
    const load = async (endpoint: string, registered: boolean) => {
      const response = await fetch(`${apiBaseUrl}/api/admin/llm-providers/${providerId}/${endpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Failed to load models");
      const ids = parseModelIds(await response.json(), registered);
      if (requestId === modelRequestId.current) {
        setAvailableModels((previous) => Array.from(new Set([...previous, ...ids])));
      }
      return ids;
    };
    const results = await Promise.allSettled([load("models", false), load("registered-models", true)]);
    if (requestId !== modelRequestId.current) return;
    setAvailableModels(Array.from(new Set(results.flatMap((result) => result.status === "fulfilled" ? result.value : []))));
    const failed = results.filter((result) => result.status === "rejected").length;
    setModelsError(failed === 2 ? "Models unavailable. Enter a model ID." : failed ? "Some models could not be loaded." : "");
    setFetchingModels(false);
  }, [apiBaseUrl]);

  useEffect(() => () => { modelRequestId.current += 1; }, []);

  useEffect(() => {
    if (routeDraftId) {
      setDraftId(routeDraftId);
      return;
    }

    const nextDraftId = crypto.randomUUID();
    setDraftId(nextDraftId);
    const params = new URLSearchParams(searchParams.toString());
    params.set("draft_id", nextDraftId);
    router.replace(`/admin/agents/${isNew ? "new" : agentId}?${params.toString()}`);
  }, [isNew, agentId, routeDraftId, router, searchParams]);

  useEffect(() => {
    if (!draftStorageKey) return;
    setLoadedDraftKey(null);
    setHydratedDraftKey(null);

    try {
      const rawDraft = sessionStorage.getItem(draftStorageKey);
      setDraftData(rawDraft ? JSON.parse(rawDraft) : null);
    } catch (error) {
      console.error("Failed to restore agent draft:", error);
      setDraftData(null);
    } finally {
      setLoadedDraftKey(draftStorageKey);
    }
  }, [draftStorageKey]);

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

  useEffect(() => {
    if (loading || !draftReady || !toolsLoaded || !agentsLoaded || draftHydrated) {
      return;
    }

    if (!draftData) {
      setHydratedDraftKey(draftStorageKey);
      return;
    }

    setFormData((prev) => ({
      ...prev,
      name: draftData.name,
      model: draftData.model.trim(),
      instructions: draftData.instructions,
      is_starting_agent: draftData.is_starting_agent,
      llm_provider_id: draftData.llm_provider_id,
      tools: availableTools.filter((tool) => draftData.tool_ids.includes(tool.id)),
      handoffs: availableAgents.filter((agent) => draftData.handoff_ids.includes(agent.id)),
    }));

    fetchModels(draftData.llm_provider_id, draftData.model.trim());

    setHydratedDraftKey(draftStorageKey);
  }, [loading, draftReady, toolsLoaded, agentsLoaded, draftHydrated, draftStorageKey, draftData, availableTools, availableAgents, fetchModels]);

  useEffect(() => {
    if (!draftStorageKey || !draftReady || !draftHydrated) {
      return;
    }

    const draftPayload: AgentDraft = {
      name: formData.name,
      model: formData.model.trim(),
      instructions: formData.instructions,
      is_starting_agent: formData.is_starting_agent,
      llm_provider_id: formData.llm_provider_id,
      tool_ids: formData.tools.map((tool) => tool.id),
      handoff_ids: formData.handoffs.map((handoff) => handoff.id),
    };

    sessionStorage.setItem(draftStorageKey, JSON.stringify(draftPayload));
  }, [draftStorageKey, draftReady, draftHydrated, formData]);

  useEffect(() => {
    if (loading || !draftHydrated || !autoSelectProviderId) return;
    const selectionKey = `${draftStorageKey}:${autoSelectProviderId}`;
    if (appliedProviderSelection.current === selectionKey) return;
    if (!availableProviders.some((provider) => provider.id === autoSelectProviderId)) return;
    appliedProviderSelection.current = selectionKey;
    if (formData.llm_provider_id === autoSelectProviderId) return;
    setFormData((prev) => ({ ...prev, llm_provider_id: autoSelectProviderId, model: "" }));
    fetchModels(autoSelectProviderId);
  }, [loading, draftHydrated, autoSelectProviderId, draftStorageKey, availableProviders, formData.llm_provider_id, fetchModels]);

  const fetchProviders = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${apiBaseUrl}/api/admin/llm-providers`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        setAvailableProviders([]);
        return;
      }
      const data = await response.json();
      setAvailableProviders(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error("Failed to fetch providers:", error);
      setAvailableProviders([]);
    }
  };

  const fetchTools = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const params = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/tools${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        setAvailableTools([]);
        return;
      }
      const data = await response.json();
      const fetchedTools = Array.isArray(data) ? data : [];
      setAvailableTools(fetchedTools);
      setFormData((prev) => {
        let tools = prev.tools;
        const dateTimeTool = fetchedTools.find((tool: Tool) => tool.name === "DateTimeTool");
        if (dateTimeTool && !tools.some((t) => t.id === dateTimeTool.id)) {
          tools = [...tools, dateTimeTool];
        }
        if (autoSelectToolId) {
          const autoTool = fetchedTools.find((tool: Tool) => tool.id === autoSelectToolId);
          if (autoTool && !tools.some((t) => t.id === autoTool.id)) {
            tools = [...tools, autoTool];
          }
        }
        if (tools === prev.tools) return prev;
        return { ...prev, tools };
      });
    } catch (error) {
      console.error("Failed to fetch tools:", error);
      setAvailableTools([]);
    } finally {
      setToolsLoaded(true);
    }
  };

  const fetchAgents = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const query = effectiveTeamId ? `?team_agent_id=${effectiveTeamId}` : "";
      const response = await fetch(`${apiBaseUrl}/api/admin/agents${query}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        setAvailableAgents([]);
        return;
      }
      const data = await response.json();
      const agents = Array.isArray(data) ? data : [];
      setAvailableAgents(
        agents.filter((a: any) => a.id !== agentId).map((a: any) => ({ id: a.id, name: a.name }))
      );
    } catch (error) {
      console.error("Failed to fetch agents:", error);
      setAvailableAgents([]);
    } finally {
      setAgentsLoaded(true);
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
      if (!response.ok) {
        return;
      }
      const data = await response.json();

      // Extract provider ID from nested object if present
      const providerId = data.llm_provider?.id || null;

      setFormData({
        ...data,
        name: typeof data.name === "string" ? data.name : "",
        model: typeof data.model === "string" ? data.model.trim() : "",
        instructions: typeof data.instructions === "string" ? data.instructions : "",
        tools: Array.isArray(data.tools) ? data.tools : [],
        handoffs: Array.isArray(data.handoffs) ? data.handoffs : [],
        llm_provider_id: providerId
      });

      fetchModels(providerId, typeof data.model === "string" ? data.model.trim() : "");
    } catch (error) {
      console.error("Failed to fetch agent:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!formData.model.trim()) {
      setError("Enter a model ID.");
      return;
    }
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
        model: formData.model.trim(),
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
      if (draftStorageKey) {
        sessionStorage.removeItem(draftStorageKey);
      }
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
    if (value === "__new_provider__") {
      router.push(newProviderHref);
      return;
    }

    const providerId = (value === "default" || value === "") ? null : parseInt(value);

    // Explicitly set undefined if it's the placeholder "Select Provider"
    const finalProviderId = value === "" ? undefined : providerId;

    setFormData({
      ...formData,
      llm_provider_id: finalProviderId,
      model: "", // Reset model when provider changes
    });

    fetchModels(finalProviderId);
  };

  const handleOptimizePrompt = async () => {
    if (!safeInstructions.trim()) {
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
            instructions: safeInstructions,
            agent_name: formData.name,
            model: formData.model.trim(),
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
        backLabel={returnTeamId ? returnToWorkflow ? "Workflow" : "Team Manage" : "Team Agents"}
        backHref={teamManageHref}
        steps={[
          { label: "Team Agents", href: returnTeamId && !returnToWorkflow ? `/admin/teams?manage_team=${returnTeamId}` : "/admin/teams" },
          ...(returnTeamId
            ? [{ label: returnTeamName || (returnToWorkflow ? "Workflow" : "Manage Team"), href: teamManageHref }]
            : []),
          { label: isNew ? "Create Agent" : "Edit Agent", active: true },
        ]}
        actions={[
          { label: "Agent Capabilities", href: `/admin/tools${capabilitiesQuery ? `?${capabilitiesQuery}` : ""}`, variant: "outline" },
          { label: "Providers", href: providersHref, variant: "outline" },
        ]}
      />

      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          {isNew ? "Create New Agent" : `Edit Agent: ${formData.name}`}
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Configure the agent's behavior, capabilities, and handoffs
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
              <label htmlFor="llm-provider" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                LLM Provider <span className="text-red-500">*</span>
              </label>
              <select
                id="llm-provider"
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
                <option value="__new_provider__">+ New Provider...</option>
              </select>
              {formData.llm_provider_id === undefined && (
                <p className="mt-1 text-xs text-red-500">
                  Please select an LLM provider to continue
                </p>
              )}
              {availableProviders.length === 0 && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Tip: You can add more providers in the{" "}
                  <Link href={newProviderHref} className="underline font-medium">
                    LLM Providers
                  </Link>{" "}
                  settings.
                </p>
              )}
            </div>

            <div>
              <label htmlFor="agent-model" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Model {fetchingModels && <span className="text-xs text-gray-400 ml-2">(Loading...)</span>}
              </label>
              <select
                id="agent-model"
                value={customModel ? CUSTOM_MODEL : formData.model}
                onChange={(e) => {
                  const custom = e.target.value === CUSTOM_MODEL;
                  setCustomModel(custom);
                  setFormData({ ...formData, model: custom ? "" : e.target.value });
                }}
                disabled={formData.llm_provider_id === undefined}
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
                {!customModel && !availableModels.includes(formData.model) && formData.model && (
                  <option value={formData.model}>{formData.model} (Current)</option>
                )}
                <option value={CUSTOM_MODEL}>+ Enter model ID…</option>
              </select>
              {customModel && (
                <div className="mt-3">
                  <label htmlFor="custom-model-id" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Model ID</label>
                  <input
                    id="custom-model-id"
                    type="text"
                    required
                    pattern={".*\\S.*"}
                    value={formData.model}
                    onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                  />
                </div>
              )}
              {modelsError && <p role="status" className="mt-1 text-xs text-amber-600 dark:text-amber-400">{modelsError}</p>}
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Instructions
                </label>
                <button
                  type="button"
                  onClick={handleOptimizePrompt}
                  disabled={optimizing || !safeInstructions.trim()}
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
                {effectiveTeamId ? "Use as team fallback" : "Set as starting agent"}
              </label>
            </div>
          </div>
        </div>

        {/* Agent Capabilities */}
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              Agent Capabilities
            </h2>
            <Link
              href={`/admin/tools${capabilitiesQuery ? `?${capabilitiesQuery}` : ""}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/20 hover:bg-blue-200 dark:hover:bg-blue-900/30 transition-colors"
            >
              <Wrench className="w-3.5 h-3.5" />
              Manage Capabilities
            </Link>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select the capabilities this agent can use
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
                    {getCapabilityDisplayName(tool)}
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
            onClick={() => {
              if (draftStorageKey) {
                sessionStorage.removeItem(draftStorageKey);
              }
              router.push(teamManageHref);
            }}
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
