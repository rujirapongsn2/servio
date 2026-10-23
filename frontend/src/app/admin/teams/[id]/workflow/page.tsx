import { notFound } from "next/navigation";
import TeamWorkflowWorkspace from "@/components/TeamWorkflowWorkspace";

export default async function TeamWorkflowPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const teamId = Number(id);
  if (!/^\d+$/.test(id) || !Number.isSafeInteger(teamId) || teamId < 1) notFound();
  return <TeamWorkflowWorkspace key={teamId} teamId={teamId} />;
}
