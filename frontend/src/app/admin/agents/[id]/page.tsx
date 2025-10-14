"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/Button";

interface Tool {
  id: number;
  name: string;
  type: string;
}

interface Agent {
  id?: number;
  name: string;
  model: string;
  instructions: string;
  is_starting_agent: boolean;
  tools: Tool[];
  handoffs: { id: number; name: string }[];
}

export default function AgentEditorPage() {
  const router = useRouter();
  const params = useParams();
  const isNew = params.id === "new";
  const agentId = isNew ? null : parseInt(params.id as string);

  const [formData, setFormData] = useState<Agent>({
    name: "",
    model: "gpt-4o-mini",
    instructions: "",
    is_starting_agent: false,
    tools: [],
    handoffs: [],
  });

  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [availableAgents, setAvailableAgents] = useState<
    { id: number; name: string }[]
  >([]);
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchTools();
    fetchAgents();
    if (!isNew && agentId) {
      fetchAgent();
    }
  }, []);

  const fetchTools = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch("http://localhost:8000/api/admin/tools", {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      setAvailableTools(data);
    } catch (error) {
      console.error("Failed to fetch tools:", error);
    }
  };

  const fetchAgents = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch("http://localhost:8000/api/admin/agents", {
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
      const response = await fetch(
        `http://localhost:8000/api/admin/agents/${agentId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await response.json();
      setFormData(data);
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
        name: formData.name,
        model: formData.model,
        instructions: formData.instructions,
        tool_ids: formData.tools.map((t) => t.id),
        handoff_agent_ids: formData.handoffs.map((h) => h.id),
        is_starting_agent: formData.is_starting_agent,
      };

      const url = isNew
        ? "http://localhost:8000/api/admin/agents"
        : `http://localhost:8000/api/admin/agents/${agentId}`;

      const response = await fetch(url, {
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

      router.push("/admin/agents");
    } catch (err: any) {
      setError(err.message || "An error occurred while saving");
    } finally {
      setSaving(false);
    }
  };

  const toggleTool = (tool: Tool) => {
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

  if (loading) {
    return (
      <div className="text-gray-600 dark:text-gray-400">Loading agent...</div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
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
                Model
              </label>
              <select
                value={formData.model}
                onChange={(e) =>
                  setFormData({ ...formData, model: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
              >
                <option value="gpt-4o-mini">gpt-4o-mini</option>
                <option value="gpt-4o">gpt-4o</option>
                <option value="gpt-4-turbo">gpt-4-turbo</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Instructions
              </label>
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
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
            Tools
          </h2>
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
            onClick={() => router.push("/admin/agents")}
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
