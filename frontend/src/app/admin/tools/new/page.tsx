"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import WorkflowNavigator from "@/components/WorkflowNavigator";
import CreateToolForm from "@/components/CreateToolForm";
import { useTeam } from "@/lib/team-context";
import { UI_COPY } from "@/lib/ui-copy";

const positiveId = (value: string | null) => { const id = Number(value); return Number.isSafeInteger(id) && id > 0 ? id : null; };

function NewToolForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { selectedTeamId, setSelectedTeamId } = useTeam();
  const routeTeamId = positiveId(searchParams.get("team_agent_id"));
  const teamId = routeTeamId ?? selectedTeamId;
  const toolsHref = `/admin/tools${teamId ? `?team_agent_id=${teamId}` : ""}`;
  return <div className="max-w-3xl space-y-6">
    <WorkflowNavigator backLabel={UI_COPY.tools.navLabel} backHref="/admin/tools" steps={[
      { label: "Team Agents", href: "/admin/teams" },
      { label: UI_COPY.tools.navLabel, href: "/admin/tools" },
      { label: "Add Integration", active: true },
    ]} />
    <h1 className="text-[26px] font-bold tracking-[-0.02em] text-gray-900 dark:text-white">Add Integration</h1>
    <CreateToolForm context={{ kind: "tools-page", teamId, assignAgentId: positiveId(searchParams.get("source_agent_id")) }} onCancel={() => router.push(toolsHref)} onCreated={(result) => {
      if (routeTeamId && routeTeamId !== selectedTeamId) setSelectedTeamId(routeTeamId);
      const returnAgentValue = searchParams.get("return_agent_id");
      const returnAgentId = returnAgentValue === "new" ? "new" : positiveId(returnAgentValue);
      if (!returnAgentId) { router.push(toolsHref); return; }
      const query = new URLSearchParams();
      if (teamId) query.set("team_agent_id", String(teamId));
      for (const key of ["return_team_id", "return_team_name", "draft_id"]) {
        const value = searchParams.get(key);
        if (value) query.set(key, value);
      }
      if (searchParams.get("return_workspace") === "workflow") query.set("return_workspace", "workflow");
      query.set("auto_select_tool_id", String(result.tool_id));
      router.push(`/admin/agents/${returnAgentId}?${query}`);
    }} />
  </div>;
}

export default function NewToolPage() {
  return <Suspense><NewToolForm /></Suspense>;
}
