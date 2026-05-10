"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { getApiBaseUrl } from "@/lib/api";
import { UI_COPY } from "@/lib/ui-copy";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";

type SessionsByTeamResponse = {
  series: Array<Record<string, string | number>>;
  teams: string[];
};

const TEAM_COLORS = [
  "#2563EB",
  "#16A34A",
  "#EA580C",
  "#7C3AED",
  "#0D9488",
  "#DB2777",
  "#CA8A04",
  "#4F46E5",
];

export default function AdminDashboard() {
  const router = useRouter();
  const apiBaseUrl = getApiBaseUrl();
  const [period, setPeriod] = useState<"day" | "week" | "month">("day");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    agentCount: 0,
    toolCount: 0,
    builtinTools: 0,
    customTools: 0,
  });
  const [chartData, setChartData] = useState<SessionsByTeamResponse>({ series: [], teams: [] });

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const token = localStorage.getItem("adminToken");
        if (!token) {
          router.push("/admin/login");
          return;
        }

        const [agentsRes, toolsRes, sessionsRes] = await Promise.all([
          fetch(`${apiBaseUrl}/api/admin/agents`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiBaseUrl}/api/admin/tools`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiBaseUrl}/api/admin/analytics/sessions-by-team?period=${period}`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);

        if (!agentsRes.ok || !toolsRes.ok || !sessionsRes.ok) {
          if (agentsRes.status === 401 || toolsRes.status === 401 || sessionsRes.status === 401) {
            localStorage.removeItem("adminToken");
            router.push("/admin/login");
            return;
          }
          throw new Error("Failed to fetch dashboard data");
        }

        const agents = await agentsRes.json();
        const tools = await toolsRes.json();
        const sessions: SessionsByTeamResponse = await sessionsRes.json();

        setStats({
          agentCount: Array.isArray(agents) ? agents.length : 0,
          toolCount: Array.isArray(tools) ? tools.length : 0,
          builtinTools: Array.isArray(tools) ? tools.filter((t: { type: string }) => t.type === "builtin").length : 0,
          customTools: Array.isArray(tools)
            ? tools.filter((t: { type: string }) =>
                t.type === "custom_api" ||
                t.type === "mcp_streamable_http" ||
                t.type === "gemini_file_search"
              ).length
            : 0,
        });

        setChartData({
          series: Array.isArray(sessions.series) ? sessions.series : [],
          teams: Array.isArray(sessions.teams) ? sessions.teams : [],
        });
      } catch (error) {
        console.error("Failed to fetch dashboard data:", error);
        setChartData({ series: [], teams: [] });
      } finally {
        setLoading(false);
      }
    };

    setLoading(true);
    fetchDashboardData();
  }, [apiBaseUrl, period, router]);

  const teamColorMap = useMemo(() => {
    const m: Record<string, string> = {};
    chartData.teams.forEach((team, i) => {
      m[team] = TEAM_COLORS[i % TEAM_COLORS.length];
    });
    return m;
  }, [chartData.teams]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Overview of your voice agent system</p>
      </div>

      {loading ? (
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard title={UI_COPY.dashboard.cards.totalAgents.title} value={stats.agentCount} description={UI_COPY.dashboard.cards.totalAgents.description} color="blue" />
            <StatCard title={UI_COPY.dashboard.cards.totalCapabilities.title} value={stats.toolCount} description={UI_COPY.dashboard.cards.totalCapabilities.description} color="green" />
            <StatCard title={UI_COPY.dashboard.cards.includedCapabilities.title} value={stats.builtinTools} description={UI_COPY.dashboard.cards.includedCapabilities.description} color="purple" />
            <StatCard title={UI_COPY.dashboard.cards.externalIntegrations.title} value={stats.customTools} description={UI_COPY.dashboard.cards.externalIntegrations.description} color="orange" />
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="mb-1 text-lg font-semibold text-gray-900 dark:text-white">Sessions per time</h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">Stacked by Team Agent</p>
              </div>
              <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
                <button
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${period === "day" ? "bg-blue-600 text-white" : "text-gray-700"}`}
                  onClick={() => setPeriod("day")}
                >
                  Day
                </button>
                <button
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${period === "week" ? "bg-blue-600 text-white" : "text-gray-700"}`}
                  onClick={() => setPeriod("week")}
                >
                  Week
                </button>
                <button
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${period === "month" ? "bg-blue-600 text-white" : "text-gray-700"}`}
                  onClick={() => setPeriod("month")}
                >
                  Month
                </button>
              </div>
            </div>

            {chartData.series.length === 0 ? (
              <div className="py-20 text-center text-sm text-gray-500">No session data in selected period</div>
            ) : (
              <div className="h-[300px] w-full rounded-lg border border-gray-100 bg-gray-50/40 p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={chartData.series}
                    margin={{ top: 6, right: 8, left: -18, bottom: 2 }}
                    barCategoryGap="28%"
                  >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB" />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 12, fill: "#6B7280" }}
                      tickLine={false}
                      axisLine={{ stroke: "#D1D5DB" }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 12, fill: "#6B7280" }}
                      tickLine={false}
                      axisLine={false}
                      width={30}
                    />
                    <Tooltip />
                    <Legend />
                    {chartData.teams.map((team) => (
                      <Bar
                        key={team}
                        dataKey={team}
                        stackId="sessions"
                        fill={teamColorMap[team]}
                        maxBarSize={36}
                        radius={[6, 6, 0, 0]}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({
  title,
  value,
  description,
  color,
}: {
  title: string;
  value: number;
  description: string;
  color: string;
}) {
  const colorClasses = {
    blue: "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400",
    green: "bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400",
    purple: "bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400",
    orange: "bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400",
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className={`inline-flex items-center justify-center w-12 h-12 rounded-lg mb-4 ${colorClasses[color as keyof typeof colorClasses]}`}>
        <span className="text-2xl font-bold">{value}</span>
      </div>
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">{title}</h3>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">{description}</p>
    </div>
  );
}
