"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTeam } from "@/lib/team-context";
import { getApiBaseUrl } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import { Plus, Trash2, Users, Bot, Pencil, Play, Wrench } from "lucide-react";

interface TeamMember {
  agent_id: number;
  agent_name: string;
  role: string;
  sort_order: number;
}

interface TeamDetail {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  member_count: number;
  members: TeamMember[];
  created_at: string;
  updated_at: string;
}

interface AgentOption {
  id: number;
  name: string;
  model: string;
  instructions: string;
  is_starting_agent: boolean;
  tools: ToolOption[];
  handoffs: { id: number; name: string }[];
  llm_provider?: { id: number; name: string } | null;
}

interface ToolOption {
  id: number;
  name: string;
  type: string;
}

export default function TeamsPage() {
  const router = useRouter();
  const { teams, loading: teamsLoading, refreshTeams, setSelectedTeamId } = useTeam();
  const [showCreate, setShowCreate] = useState(false);
  const [editingTeam, setEditingTeam] = useState<TeamDetail | null>(null);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [memberAgentIds, setMemberAgentIds] = useState<number[]>([]);
  const [startingAgentId, setStartingAgentId] = useState<number | null>(null);
  const [membersSaveState, setMembersSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [pageMessage, setPageMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const apiBase = getApiBaseUrl();
  const token = typeof window !== "undefined" ? localStorage.getItem("adminToken") : "";

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const manageTeamId = params.get("manage_team");
    if (manageTeamId) {
      openEdit(parseInt(manageTeamId));
      router.replace("/admin/teams");
    }
  }, []);

  const slugify = (value: string) =>
    value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");

  const handleCreate = async () => {
    const name = formName.trim();
    if (!name) return;
    const slug = slugify(name);
    const res = await fetch(`${apiBase}/api/admin/team-agents`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ name, slug, description: formDesc }),
    });
    if (res.ok) {
      setShowCreate(false);
      setFormName("");
      setFormDesc("");
      refreshTeams();
    }
  };

  const handleDelete = async (teamId: number) => {
    if (!confirm("Are you sure you want to delete this team?")) return;
    const res = await fetch(`${apiBase}/api/admin/team-agents/${teamId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setPageMessage({ type: "success", text: "Team deleted." });
      refreshTeams();
      return;
    }
    const data = await res.json().catch(() => ({}));
    setPageMessage({ type: "error", text: data.detail || "Failed to delete team" });
  };

  const openEdit = async (teamId: number) => {
    setMembersSaveState("idle");
    setSelectedTeamId(teamId);
    const [teamRes, agentsRes] = await Promise.all([
      fetch(`${apiBase}/api/admin/team-agents/${teamId}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${apiBase}/api/admin/agents?team_agent_id=${teamId}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ]);

    if (teamRes.ok) {
      const data: TeamDetail = await teamRes.json();
      setEditingTeam(data);
      setMemberAgentIds(data.members.map((m) => m.agent_id));
      setStartingAgentId(data.members.find((m) => m.role === "starting")?.agent_id ?? null);
    }

    if (agentsRes.ok) {
      const data: AgentOption[] = await agentsRes.json();
      setAgents(data);
    }
  };

  const openAgentEditor = (agentId: number | "new") => {
    if (!editingTeam) return;
    setSelectedTeamId(editingTeam.id);
    const target = agentId === "new" ? "new" : String(agentId);
    const params = new URLSearchParams({
      team_agent_id: String(editingTeam.id),
      return_team_id: String(editingTeam.id),
      return_team_name: editingTeam.name,
    });
    if (agentId === "new") {
      params.set("draft_id", crypto.randomUUID());
    }
    router.push(`/admin/agents/${target}?${params}`);
  };

  const openAgentTester = (agentId: number) => {
    if (!editingTeam) return;
    setSelectedTeamId(editingTeam.id);
    const params = new URLSearchParams({
      team_agent_id: String(editingTeam.id),
      return_team_id: String(editingTeam.id),
      return_team_name: editingTeam.name,
    });
    router.push(`/admin/agents/${agentId}/test?${params}`);
  };

  const toggleMember = (agentId: number) => {
    setMembersSaveState("idle");
    setMemberAgentIds((prev) => {
      if (prev.includes(agentId)) {
        const next = prev.filter((id) => id !== agentId);
        if (startingAgentId === agentId) {
          setStartingAgentId(next[0] ?? null);
        }
        return next;
      }
      if (!startingAgentId) {
        setStartingAgentId(agentId);
      }
      return [...prev, agentId];
    });
  };

  const handleDeleteAgent = async (agentId: number) => {
    if (!editingTeam) return;
    if (!confirm("Delete this agent? This removes it from all teams.")) return;
    const res = await fetch(`${apiBase}/api/admin/agents/${agentId}?team_agent_id=${editingTeam.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      await openEdit(editingTeam.id);
      await refreshTeams();
    } else {
      alert("Failed to delete agent");
    }
  };

  const handleSaveMembers = async () => {
    if (!editingTeam) return;
    setMembersSaveState("saving");
    const effectiveStarting = startingAgentId && memberAgentIds.includes(startingAgentId)
      ? startingAgentId
      : memberAgentIds[0] ?? null;
    const res = await fetch(`${apiBase}/api/admin/team-agents/${editingTeam.id}/members`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        member_agent_ids: memberAgentIds,
        starting_agent_id: effectiveStarting,
      }),
    });

    if (res.ok) {
      await refreshTeams();
      await openEdit(editingTeam.id);
      setMembersSaveState("saved");
    } else {
      setMembersSaveState("idle");
      const error = await res.json().catch(() => ({}));
      alert(error.detail || "Failed to update team members");
    }
  };

  return (
    <div className="space-y-8">
      <WorkflowNavigator
        backLabel="Dashboard"
        backHref="/admin"
        steps={[
          { label: "Dashboard", href: "/admin" },
          { label: "Team Agents", active: true },
        ]}
        actions={[
          { label: "Channels", href: "/admin/tools/channels", variant: "outline" },
          { label: "Online Agent", href: "/admin/monitor", variant: "outline" },
          { label: "Analytics", href: "/admin/analytics", variant: "outline" },
        ]}
      />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[26px] font-bold leading-tight tracking-[-0.02em] text-ink">Team Agents</h1>
          <p className="mt-1 text-base font-medium text-ink-3">
            Manage your agent teams and workspaces
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-1" /> New Team
        </Button>
      </div>

      {pageMessage && (
        <div
          className={`rounded-md border px-3 py-2 text-sm ${
            pageMessage.type === "success"
              ? "border-green-200 bg-green-50 text-green-700 dark:border-green-900/40 dark:bg-green-900/20 dark:text-green-300"
              : "border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
          }`}
        >
          {pageMessage.text}
        </div>
      )}

      {/* Team Cards */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {teams.map((team) => (
          <div
            key={team.id}
            className="rounded-[14px] border border-line bg-white p-6 transition-colors hover:border-line-strong"
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-semibold text-ink">{team.name}</h3>
                <p className="text-sm font-medium text-ink-3">{team.slug}</p>
                <p className="mt-1 text-xs font-medium text-gray-400">
                  Owned by: {team.owner_username || "N/A"}
                </p>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                  team.status === "active"
                    ? "bg-surface-2 text-primary ring-1 ring-line"
                    : "bg-surface-2 text-ink-3 ring-1 ring-line"
                }`}
              >
                {team.status}
              </span>
            </div>

            {team.description && (
              <p className="mt-3 line-clamp-2 text-sm font-medium leading-5 text-ink-2">
                {team.description}
              </p>
            )}

            <div className="mt-5 flex items-center gap-4 text-sm font-medium text-ink-3">
              <span className="flex items-center gap-1">
                <Users className="h-4 w-4" /> {team.member_count} agents
              </span>
              {team.starting_agent_name && (
                <span className="flex items-center gap-1">
                  <Bot className="h-4 w-4" /> {team.starting_agent_name}
                </span>
              )}
            </div>

            <div className="mt-5 flex items-center gap-2 border-t border-line pt-4">
              <Button variant="outline" size="sm" onClick={() => openEdit(team.id)}>
                Manage
              </Button>
              <Button variant="outline" size="sm" onClick={() => router.push(`/admin/teams/${team.id}/workflow`)}>
                Workflow
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleDelete(team.id)}
                className="border-red-200 text-red-600 hover:border-red-300 hover:text-red-700"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}

        {teamsLoading && (
          <div className="col-span-full rounded-[14px] border border-dashed border-line-strong py-12 text-center text-sm font-medium text-ink-3">
            Loading team agents...
          </div>
        )}

        {!teamsLoading && teams.length === 0 && (
          <div className="col-span-full rounded-[14px] border border-dashed border-line-strong py-12 text-center text-sm font-medium text-ink-3">
            No teams yet. Create your first team to get started.
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-y-0 right-0 z-50 flex items-center justify-center bg-black/[0.24] px-4 [left:var(--admin-sidebar-width)]">
          <div className="w-full max-w-md rounded-[20px] border border-line bg-white p-6 shadow-[rgba(0,0,0,0.02)_0_0_0_1px,rgba(0,0,0,0.04)_0_2px_6px_0,rgba(0,0,0,0.1)_0_4px_8px_0]">
            <h2 className="mb-4 text-[22px] font-medium leading-[1.18] tracking-[-0.44px] text-ink">Create Team Agent</h2>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-ink-2">
                  Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full rounded-lg border border-line bg-white px-4 py-3 text-sm font-medium text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink"
                  placeholder="Sales Support"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-ink-2">
                  Description
                </label>
                <textarea
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="w-full rounded-lg border border-line bg-white px-4 py-3 text-sm font-medium text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink"
                  rows={3}
                  placeholder="Optional description..."
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button onClick={handleCreate} disabled={!formName.trim()}>
                Create
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingTeam && (
        <div className="fixed inset-y-0 right-0 z-50 flex items-center justify-center bg-black/[0.24] px-4 [left:var(--admin-sidebar-width)]">
          <div className="max-h-[88vh] w-full max-w-[1200px] overflow-y-auto rounded-[20px] border border-line bg-white p-6 shadow-[rgba(0,0,0,0.02)_0_0_0_1px,rgba(0,0,0,0.04)_0_2px_6px_0,rgba(0,0,0,0.1)_0_4px_8px_0]">
            <WorkflowNavigator
              backLabel="Close"
              onBack={() => setEditingTeam(null)}
              steps={[
                { label: "Team Agents", href: "/admin/teams" },
                { label: editingTeam.name, active: true },
              ]}
            />
            <div className="mt-6">
              <section>
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-[22px] font-medium leading-[1.18] tracking-[-0.44px] text-ink">
                      {editingTeam.name} — Members
                    </h2>
                    <p className="mt-1 text-sm font-medium text-ink-3">
                      Select members and choose the fallback agent.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedTeamId(editingTeam.id);
                      const autoAssignAgentId =
                        startingAgentId ?? (memberAgentIds.length === 1 ? memberAgentIds[0] : null);
                      const params = new URLSearchParams({
                        team_agent_id: String(editingTeam.id),
                        return_to: "team_manage",
                        return_team_id: String(editingTeam.id),
                        return_team_name: editingTeam.name,
                      });
                      if (autoAssignAgentId) {
                        params.set("source_agent_id", String(autoAssignAgentId));
                      }
                      router.push(`/admin/tools?${params.toString()}`);
                    }}
                  >
                    Manage Team Capabilities
                  </Button>
                </div>
                <div className="overflow-hidden rounded-[14px] border border-line">
                  <table className="w-full divide-y divide-line">
                    <thead className="bg-surface-2">
                      <tr>
                        <th className="w-24 px-4 py-3 text-left text-[12.5px] font-semibold text-ink-3">
                          Member
                        </th>
                        <th className="w-28 px-4 py-3 text-left text-[12.5px] font-semibold text-ink-3">
                          Fallback
                        </th>
                        <th className="px-4 py-3 text-left text-[12.5px] font-semibold text-ink-3">
                          Agent
                        </th>
                        <th className="w-36 px-4 py-3 text-right text-[12.5px] font-semibold text-ink-3">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line bg-white">
                      {agents.map((agent) => {
                        const isMember = memberAgentIds.includes(agent.id);
                        return (
                          <tr key={agent.id} className="hover:bg-surface-2">
                            <td className="px-4 py-3">
                              <input
                                type="checkbox"
                                checked={isMember}
                                onChange={() => toggleMember(agent.id)}
                                className="h-4 w-4"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="radio"
                                name="starting-agent"
                                checked={startingAgentId === agent.id}
                                disabled={!isMember}
                                onChange={() => {
                                  setStartingAgentId(agent.id);
                                  setMembersSaveState("idle");
                                }}
                                className="h-4 w-4"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <div className="font-semibold text-ink">{agent.name}</div>
                              <div className="text-xs font-medium text-ink-3">
                                {agent.model}
                                {agent.tools.length > 0 && (
                                  <span className="ml-2 inline-flex items-center gap-0.5">
                                    <Wrench className="h-3 w-3" /> {agent.tools.length} tool(s)
                                  </span>
                                )}
                              </div>
                              <div className="mt-1 line-clamp-1 text-xs font-medium text-gray-400">
                                {agent.instructions}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex justify-end gap-1">
                                <button
                                  type="button"
                                  onClick={() => openAgentTester(agent.id)}
                                  className="rounded-full p-1.5 text-ink hover:bg-surface-2"
                                  title="Test agent"
                                >
                                  <Play className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => openAgentEditor(agent.id)}
                                  className="rounded-full p-1.5 text-primary hover:bg-surface-2"
                                  title="Edit agent"
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDeleteAgent(agent.id)}
                                  className="rounded-full p-1.5 text-red-600 hover:bg-red-50"
                                  title="Delete agent"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                      {agents.length === 0 && (
                        <tr>
                          <td colSpan={4} className="px-4 py-10 text-center text-sm font-medium text-ink-3">
                            No agents available. Create one first.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => openAgentEditor("new")}>
                Create New Agent
              </Button>
              <Button variant="outline" onClick={() => setEditingTeam(null)}>
                Close
              </Button>
              <Button
                onClick={handleSaveMembers}
                disabled={memberAgentIds.length === 0 || membersSaveState === "saving"}
              >
                {membersSaveState === "saving"
                  ? "Saving..."
                  : membersSaveState === "saved"
                    ? "Saved"
                    : "Save Members"}
              </Button>
            </div>
          </div>
        </div>
      )}


    </div>
  );
}
