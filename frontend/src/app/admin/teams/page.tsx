"use client";

import { useAdminLocale } from "@/lib/admin-locale";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTeam } from "@/lib/team-context";
import { getApiBaseUrl } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import {
  Plus,
  Trash2,
  Pencil,
  Play,
  Wrench,
  Search,
  X,
  Workflow as WorkflowIcon,
} from "lucide-react";

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

type PageMessage = { kind: "created" | "deleted" } | { kind: "create-failed" | "delete-failed"; detail?: string };

interface ToolOption {
  id: number;
  name: string;
  type: string;
}

export default function TeamsPage() {
  const { copy } = useAdminLocale();
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
  const [pageMessage, setPageMessage] = useState<PageMessage | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  const normalizedQuery = query.trim().toLowerCase();
  const visibleTeams = useMemo(() => {
    if (!normalizedQuery) return teams;
    return teams.filter((team) =>
      [team.name, team.slug, team.description, team.owner_username, team.starting_agent_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery))
    );
  }, [teams, normalizedQuery]);

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
    if (!name || creating || localStorage.getItem("isViewerOnly") === "1") return;
    const slug = slugify(name) || `team-${crypto.randomUUID()}`;
    setCreating(true);
    setPageMessage(null);
    try {
      const res = await fetch(`${apiBase}/api/admin/team-agents`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name, slug, description: formDesc }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(typeof data.detail === "string" ? data.detail : "");
      }
      setShowCreate(false); setFormName(""); setFormDesc("");
      setPageMessage({ kind: "created" });
      await refreshTeams().catch(() => {});
    } catch (error) {
      setPageMessage({ kind: "create-failed", detail: error instanceof Error ? error.message : undefined });
    } finally { setCreating(false); }
  };

  const handleDelete = async (teamId: number, teamName: string) => {
    if (localStorage.getItem("isViewerOnly") === "1" || !confirm(copy.confirmDeleteTeam(teamName))) return;
    const res = await fetch(`${apiBase}/api/admin/team-agents/${teamId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setPageMessage({ kind: "deleted" });
      refreshTeams();
      return;
    }
    const data = await res.json().catch(() => ({}));
    setPageMessage({ kind: "delete-failed", detail: typeof data.detail === "string" ? data.detail : undefined });
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
    if (!confirm(copy.confirmDeleteAgentEverywhere)) return;
    const res = await fetch(`${apiBase}/api/admin/agents/${agentId}?team_agent_id=${editingTeam.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      await openEdit(editingTeam.id);
      await refreshTeams();
    } else {
      alert(copy.deleteAgentFailed);
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
      alert(error.detail || copy.saveMembersFailed);
    }
  };

  return (
    <div className="space-y-6">
      <WorkflowNavigator
        backLabel={copy.dashboard}
        backHref="/admin"
        steps={[
          { label: copy.dashboard, href: "/admin" },
          { label: copy.teamAgents, active: true },
        ]}
        actions={[
          { label: copy.channels, href: "/admin/tools/channels", variant: "outline" },
          { label: copy.onlineAgents, href: "/admin/monitor", variant: "outline" },
          { label: copy.analytics, href: "/admin/analytics", variant: "outline" },
        ]}
      />

      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[28px] font-bold leading-[1.25] text-[#0D1B2A]">{copy.teamAgents}</h1>
        </div>
        <Button data-admin-write="true" onClick={() => setShowCreate(true)} className="self-start sm:self-auto">
          <Plus className="h-4 w-4" /> {copy.newTeam}
        </Button>
      </header>

      {pageMessage && (
        <div
          role={pageMessage.kind.endsWith("failed") ? "alert" : "status"}
          className={`flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm font-medium ${
            !pageMessage.kind.endsWith("failed")
              ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900/40 dark:bg-green-900/20 dark:text-green-300"
              : "border-red-200 bg-red-50 text-red-800 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
          }`}
        >
          <div>{pageMessage.kind === "created" ? copy.teamCreated : pageMessage.kind === "deleted" ? copy.teamDeleted : pageMessage.kind === "create-failed" ? copy.createTeamFailed : copy.deleteTeamFailed}{"detail" in pageMessage && pageMessage.detail && <details className="mt-1 text-xs"><summary>{copy.errorDetails}</summary>{pageMessage.detail}</details>}</div>
          <button
            type="button"
            onClick={() => setPageMessage(null)}
            aria-label={copy.dismissMessage}
            className="-m-1 rounded-md p-1 opacity-70 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0D1B2A]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <section aria-labelledby="team-list-heading" className="space-y-4">
        <h2 id="team-list-heading" className="sr-only">
          {copy.teams}
        </h2>

        {!teamsLoading && teams.length > 0 && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <label htmlFor="team-search" className="sr-only">
                {copy.searchTeams}
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#778DA9]"
              />
              <input
                id="team-search"
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={copy.searchTeamsHint}
                className="h-9 w-full rounded-lg border border-[#E2E8F0] bg-white pl-9 pr-3 text-sm font-medium text-[#0D1B2A] outline-none placeholder:text-[#778DA9] focus:border-[#0D1B2A] focus:ring-2 focus:ring-[#0D1B2A]/15"
              />
            </div>
            <p className="text-sm font-medium tabular-nums text-[#778DA9]" aria-live="polite">
              {normalizedQuery
                ? copy.teamsFiltered(visibleTeams.length, teams.length)
                : copy.teamsCount(teams.length)}
            </p>
          </div>
        )}

        <div
          role="list"
          className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,16.5rem),1fr))] gap-3"
        >
          {visibleTeams.map((team) => {
            const isActive = team.status === "active";
            const agentLabel = copy.agentsCount(team.member_count);
            return (
              <div
                role="listitem"
                key={team.id}
                className="flex min-w-0 flex-col rounded-xl border border-[#E2E8F0] bg-white transition-colors hover:border-[#CBD5E1]"
              >
                <div className="flex flex-1 flex-col px-4 pb-3 pt-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <h3
                      className="min-w-0 truncate text-[15px] font-semibold leading-5 text-[#0D1B2A]"
                      title={team.name}
                    >
                      {team.name}
                    </h3>
                    <span
                      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-px text-[11px] font-semibold capitalize leading-4 ring-1 ring-inset ${
                        isActive
                          ? "bg-[#2786C2]/[0.06] text-[#1A5A8A] ring-[#2786C2]/20"
                          : "bg-[#F8F9FA] text-[#2D3F55] ring-[#E2E8F0]"
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`h-1.5 w-1.5 rounded-full ${isActive ? "bg-[#2786C2]" : "bg-[#9BA8B4]"}`}
                      />
                      {team.status === "active" ? copy.active : team.status === "inactive" ? copy.inactive : team.status}
                    </span>
                  </div>

                  <p className="mt-0.5 truncate text-xs font-medium leading-4 text-[#778DA9]">
                    <span title={team.slug}>{team.slug}</span>
                    <span aria-hidden="true"> · </span>
                    <span>{copy.ownedBy(team.owner_username || "N/A")}</span>
                  </p>

                  {team.description && (
                    <p
                      className="mt-2 truncate text-[13px] font-medium leading-5 text-[#2D3F55]"
                      title={team.description}
                    >
                      {team.description}
                    </p>
                  )}

                  <p className="mt-auto flex min-w-0 items-center gap-1 pt-2 text-[13px] leading-5 text-[#778DA9]">
                    <span className="shrink-0 font-semibold tabular-nums text-[#0D1B2A]">{agentLabel}</span>
                    <span aria-hidden="true" className="shrink-0">·</span>
                    <span className="shrink-0">{copy.fallback}:</span>
                    <span
                      className={`truncate ${team.starting_agent_name ? "font-medium text-[#0D1B2A]" : ""}`}
                      title={team.starting_agent_name || undefined}
                    >
                      {team.starting_agent_name || copy.notSet}
                    </span>
                  </p>
                </div>

                <div className="flex items-center gap-1.5 border-t border-[#E2E8F0] px-3 py-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 px-2.5"
                    onClick={() => router.push(`/admin/teams/${team.id}/workflow`)}
                  >
                    <WorkflowIcon aria-hidden="true" /> {copy.workflow}
                  </Button>
                  <Button
                    variant="ghost"
                    size="iconSmall"
                    data-admin-write="true" onClick={() => handleDelete(team.id, team.name)}
                    aria-label={copy.deleteTeam(team.name)}
                    title={copy.deleteTeam(team.name)}
                    className="ml-auto h-7 w-7 text-[#778DA9] hover:bg-red-50 hover:text-[#B91C1C] focus-visible:ring-[#B91C1C]"
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>

        {teamsLoading && (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,16.5rem),1fr))] gap-3" aria-busy="true">
            <span className="sr-only">{copy.loadingTeams}</span>
            {[0, 1, 2].map((i) => (
              <div key={i} aria-hidden="true" className="h-[132px] animate-pulse rounded-xl border border-[#E2E8F0] bg-[#F8F9FA]" />
            ))}
          </div>
        )}

        {!teamsLoading && teams.length === 0 && (
          <div className="rounded-[14px] border border-dashed border-[#CBD5E1] px-6 py-12 text-center">
            <p className="text-base font-semibold text-[#0D1B2A]">{copy.noTeams}</p>
            <Button data-admin-write="true" className="mt-5" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" /> {copy.newTeam}
            </Button>
          </div>
        )}

        {!teamsLoading && teams.length > 0 && visibleTeams.length === 0 && (
          <div className="rounded-[14px] border border-dashed border-[#CBD5E1] px-6 py-12 text-center">
            <p className="text-base font-semibold text-[#0D1B2A]">{copy.noTeamsMatch(query.trim())}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => setQuery("")}>
              {copy.clearSearch}
            </Button>
          </div>
        )}
      </section>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/[0.24] px-4">
          <div className="w-full max-w-md rounded-[20px] border border-[#E2E8F0] bg-white p-6 shadow-[rgba(0,0,0,0.02)_0_0_0_1px,rgba(0,0,0,0.04)_0_2px_6px_0,rgba(0,0,0,0.1)_0_4px_8px_0]">
            <h2 className="mb-4 text-[22px] font-medium leading-[1.18] tracking-[-0.44px] text-[#0D1B2A]">{copy.createTeam}</h2>
            {pageMessage?.kind === "create-failed" && <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-sm text-red-700">{copy.createTeamFailed}{pageMessage.detail && <details><summary>{copy.errorDetails}</summary>{pageMessage.detail}</details>}</div>}
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-[#2D3F55]">
                  {copy.teamName}
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full rounded-lg border border-[#E2E8F0] bg-white px-4 py-3 text-sm font-medium text-[#0D1B2A] outline-none focus:border-[#0D1B2A] focus:ring-2 focus:ring-[#0D1B2A]"
                  placeholder={copy.teamExample}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[#2D3F55]">
                  {copy.description}
                </label>
                <textarea
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  className="w-full rounded-lg border border-[#E2E8F0] bg-white px-4 py-3 text-sm font-medium text-[#0D1B2A] outline-none focus:border-[#0D1B2A] focus:ring-2 focus:ring-[#0D1B2A]"
                  rows={3}
                  placeholder={copy.optionalDescription}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                {copy.cancel}
              </Button>
              <Button data-admin-write="true" onClick={handleCreate} disabled={!formName.trim() || creating}>
                {copy.create}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingTeam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/[0.24] px-4">
          <div className="max-h-[88vh] w-full max-w-[1200px] overflow-y-auto rounded-[20px] border border-[#E2E8F0] bg-white p-6 shadow-[rgba(0,0,0,0.02)_0_0_0_1px,rgba(0,0,0,0.04)_0_2px_6px_0,rgba(0,0,0,0.1)_0_4px_8px_0]">
            <WorkflowNavigator
              backLabel={copy.close}
              onBack={() => setEditingTeam(null)}
              steps={[
                { label: copy.teamAgents, href: "/admin/teams" },
                { label: editingTeam.name, active: true },
              ]}
            />
            <div className="mt-6">
              <section>
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-[22px] font-medium leading-[1.18] tracking-[-0.44px] text-[#0D1B2A]">
                      {editingTeam.name} · {copy.members}
                    </h2>
                    <p className="mt-1 text-sm font-medium text-[#778DA9]">
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    data-admin-write="true" onClick={() => {
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
                    {copy.manageCapabilities}
                  </Button>
                </div>
                <div className="overflow-hidden rounded-[14px] border border-[#E2E8F0]">
                  <table className="w-full divide-y divide-[#E2E8F0]">
                    <thead className="bg-[#F8F9FA]">
                      <tr>
                        <th className="w-24 px-4 py-3 text-left text-xs font-semibold text-[#778DA9]">
                          {copy.member}
                        </th>
                        <th className="w-28 px-4 py-3 text-left text-xs font-semibold text-[#778DA9]">
                          {copy.fallback}
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold text-[#778DA9]">
                          {copy.agent}
                        </th>
                        <th className="w-36 px-4 py-3 text-right text-xs font-semibold text-[#778DA9]">
                          {copy.actions}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E2E8F0] bg-white">
                      {agents.map((agent) => {
                        const isMember = memberAgentIds.includes(agent.id);
                        return (
                          <tr key={agent.id} className="hover:bg-[#F8F9FA]">
                            <td className="px-4 py-3">
                              <input
                                type="checkbox"
                                checked={isMember}
                                data-admin-write="true" onChange={() => toggleMember(agent.id)}
                                className="h-4 w-4"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="radio"
                                name="starting-agent"
                                checked={startingAgentId === agent.id}
                                disabled={!isMember}
                                data-admin-write="true" onChange={() => {
                                  setStartingAgentId(agent.id);
                                  setMembersSaveState("idle");
                                }}
                                className="h-4 w-4"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <div className="font-semibold text-[#0D1B2A]">{agent.name}</div>
                              <div className="text-xs font-medium text-[#778DA9]">
                                {agent.model}
                                {agent.tools.length > 0 && (
                                  <span className="ml-2 inline-flex items-center gap-0.5">
                                    <Wrench className="h-3 w-3" /> {copy.toolCount(agent.tools.length)}
                                  </span>
                                )}
                              </div>
                              <div className="mt-1 line-clamp-1 text-xs font-medium text-[#9BA8B4]">
                                {agent.instructions}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex justify-end gap-1">
                                <button
                                  type="button"
                                  onClick={() => openAgentTester(agent.id)}
                                  className="rounded-full p-1.5 text-[#0D1B2A] hover:bg-[#F8F9FA]"
                                  title={copy.testAgent}
                                >
                                  <Play className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  data-admin-write="true" onClick={() => openAgentEditor(agent.id)}
                                  className="rounded-full p-1.5 text-[#2786C2] hover:bg-[#F8F9FA]"
                                  title={copy.editAgent}
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  data-admin-write="true" onClick={() => handleDeleteAgent(agent.id)}
                                  className="rounded-full p-1.5 text-red-600 hover:bg-red-50"
                                  title={copy.deleteAgent}
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
                          <td colSpan={4} className="px-4 py-10 text-center text-sm font-medium text-[#778DA9]">
                            {copy.noAgentsAvailable}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" data-admin-write="true" onClick={() => openAgentEditor("new")}>
                {copy.createNewAgent}
              </Button>
              <Button variant="outline" onClick={() => setEditingTeam(null)}>
                {copy.close}
              </Button>
              <Button
                data-admin-write="true" onClick={handleSaveMembers}
                disabled={memberAgentIds.length === 0 || membersSaveState === "saving"}
              >
                {membersSaveState === "saving"
                  ? copy.saving
                  : membersSaveState === "saved"
                    ? copy.saved
                    : copy.saveMembers}
              </Button>
            </div>
          </div>
        </div>
      )}


    </div>
  );
}
