"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { getApiBaseUrl } from "@/lib/api";

interface TeamAgent {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  member_count: number;
  starting_agent_name: string | null;
  created_at: string;
  updated_at: string;
}

interface TeamContextType {
  teams: TeamAgent[];
  selectedTeamId: number | null;
  selectedTeam: TeamAgent | null;
  setSelectedTeamId: (id: number | null) => void;
  loading: boolean;
  refreshTeams: () => Promise<void>;
}

const TeamContext = createContext<TeamContextType>({
  teams: [],
  selectedTeamId: null,
  selectedTeam: null,
  setSelectedTeamId: () => {},
  loading: true,
  refreshTeams: async () => {},
});

export function TeamProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [teams, setTeams] = useState<TeamAgent[]>([]);
  const [selectedTeamId, setSelectedTeamIdState] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchTeams = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("adminToken");
      if (!token) {
        setTeams([]);
        setSelectedTeamIdState(null);
        return;
      }
      const apiBase = getApiBaseUrl();
      const res = await fetch(`${apiBase}/api/admin/team-agents`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (res.ok) {
        const data: TeamAgent[] = await res.json();
        setTeams(data);

        // Restore or default selected team
        const stored = localStorage.getItem("selectedTeamId");
        if (stored && data.find((t) => t.id === parseInt(stored))) {
          setSelectedTeamIdState(parseInt(stored));
        } else if (data.length > 0) {
          setSelectedTeamIdState(data[0].id);
        } else {
          setSelectedTeamIdState(null);
        }
      } else if (res.status === 401 || res.status === 403) {
        setTeams([]);
        setSelectedTeamIdState(null);
      }
    } catch {
      // Silently fail - team selector will show empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (pathname !== "/admin/login") {
      fetchTeams();
    } else {
      setTeams([]);
      setSelectedTeamIdState(null);
      setLoading(false);
    }
  }, [fetchTeams, pathname]);

  const setSelectedTeamId = useCallback((id: number | null) => {
    setSelectedTeamIdState(id);
    if (id != null) {
      localStorage.setItem("selectedTeamId", String(id));
    } else {
      localStorage.removeItem("selectedTeamId");
    }
  }, []);

  const selectedTeam = teams.find((t) => t.id === selectedTeamId) ?? null;

  return (
    <TeamContext.Provider
      value={{ teams, selectedTeamId, selectedTeam, setSelectedTeamId, loading, refreshTeams: fetchTeams }}
    >
      {children}
    </TeamContext.Provider>
  );
}

export function useTeam() {
  return useContext(TeamContext);
}
