"use client";

import { useTeam } from "@/lib/team-context";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown } from "lucide-react";

interface TeamSwitcherProps {
  label?: string;
}

export default function TeamSwitcher({ label }: TeamSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { teams, selectedTeam, setSelectedTeamId, loading } = useTeam();

  if (loading || teams.length <= 1) return null;

  const handleTeamChange = (teamId: number) => {
    setSelectedTeamId(teamId);

    const params = new URLSearchParams(window.location.search);
    if (params.has("team_agent_id")) {
      params.set("team_agent_id", String(teamId));
      router.replace(`${pathname}?${params.toString()}`);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {label && (
        <span className="text-xs font-semibold uppercase tracking-wide text-[#778DA9]">
          {label}
        </span>
      )}
      <div className="relative inline-block">
        <select
          value={selectedTeam?.id ?? ""}
          onChange={(e) => handleTeamChange(parseInt(e.target.value))}
          aria-label={label || "Team Agent"}
          className="appearance-none rounded-full border border-[#E2E8F0] bg-white py-2 pl-4 pr-9 text-sm font-medium text-[#0D1B2A] shadow-[rgba(0,0,0,0.04)_0_2px_6px_0] outline-none focus:border-[#0D1B2A] focus:ring-2 focus:ring-[#0D1B2A] cursor-pointer"
        >
          {teams.map((team) => (
            <option key={team.id} value={team.id} className="text-gray-900 bg-white">
              {team.name}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#778DA9] pointer-events-none" />
      </div>
    </div>
  );
}
