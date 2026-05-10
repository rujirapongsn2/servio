"use client";

import { useTeam } from "@/lib/team-context";
import { ChevronDown } from "lucide-react";

export default function TeamSwitcher() {
  const { teams, selectedTeam, setSelectedTeamId, loading } = useTeam();

  if (loading || teams.length <= 1) return null;

  return (
    <div className="relative inline-block">
      <select
        value={selectedTeam?.id ?? ""}
        onChange={(e) => setSelectedTeamId(parseInt(e.target.value))}
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
  );
}
