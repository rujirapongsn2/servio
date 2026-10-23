"use client";
import { Suspense } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import EditToolForm from "@/components/EditToolForm";
import { useTeam } from "@/lib/team-context";
function EditIntegration() {
  const params = useParams();
  const search = useSearchParams();
  const router = useRouter();
  const { selectedTeamId } = useTeam();
  const toolId = Number(params.id);
  const teamId = Number(search.get("team_agent_id")) || selectedTeamId;
  const returnQuery = new URLSearchParams(search.toString());
  const back = `/admin/tools${returnQuery.size ? `?${returnQuery}` : ""}`;
  if (!Number.isSafeInteger(toolId) || toolId < 1)
    return <p role="alert">Invalid integration</p>;
  return <div className="max-w-2xl space-y-4">
  <h1 className="text-2xl font-semibold">Edit Integration</h1>
  <EditToolForm toolId={toolId} teamId={teamId} onSaved={() => router.push(back)} onCancel={() => router.push(back)}/>
  </div>;
}
export default function EditToolPage() {
  return <Suspense>
  <EditIntegration />
  </Suspense>;
}
