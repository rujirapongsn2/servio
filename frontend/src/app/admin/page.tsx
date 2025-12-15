"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getApiBaseUrl } from "@/lib/api";
import dynamic from "next/dynamic";

const AgentFlowGraph = dynamic(
  () => import("@/components/AgentFlowGraph"),
  { ssr: false }
);

export default function AdminDashboard() {
  const router = useRouter();
  const apiBaseUrl = getApiBaseUrl();
  const [stats, setStats] = useState({
    agentCount: 0,
    toolCount: 0,
    builtinTools: 0,
    customTools: 0,
    agents: [] as any[],
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const token = localStorage.getItem("adminToken");

      // Redirect to login if no token
      if (!token) {
        router.push("/admin/login");
        return;
      }

      const [agentsRes, toolsRes] = await Promise.all([
        fetch(`${apiBaseUrl}/api/admin/agents`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${apiBaseUrl}/api/admin/tools`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      // Check for authentication errors
      if (!agentsRes.ok || !toolsRes.ok) {
        if (agentsRes.status === 401 || toolsRes.status === 401) {
          localStorage.removeItem("adminToken");
          router.push("/admin/login");
          return;
        }
        throw new Error("Failed to fetch data");
      }

      const agents = await agentsRes.json();
      const tools = await toolsRes.json();

      setStats({
        agentCount: Array.isArray(agents) ? agents.length : 0,
        toolCount: Array.isArray(tools) ? tools.length : 0,
        builtinTools: Array.isArray(tools) ? tools.filter((t: any) => t.type === "builtin").length : 0,
        customTools: Array.isArray(tools) ? tools.filter((t: any) => t.type === "custom_api").length : 0,
        agents: Array.isArray(agents) ? agents : [],
      });
    } catch (error) {
      console.error("Failed to fetch stats:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Dashboard
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Overview of your voice agent system
        </p>
      </div>

      {loading ? (
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      ) : (
        <>
          {/* Stats Grid */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              title="Total Agents"
              value={stats.agentCount}
              description="Active AI agents"
              color="blue"
            />
            <StatCard
              title="Total Tools"
              value={stats.toolCount}
              description="Available tools"
              color="green"
            />
            <StatCard
              title="Built-in Tools"
              value={stats.builtinTools}
              description="System tools"
              color="purple"
            />
            <StatCard
              title="Custom Tools"
              value={stats.customTools}
              description="API integrations"
              color="orange"
            />
          </div>

          {/* Quick Actions */}
          <div className="mt-8">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Quick Actions
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <ActionCard
                title="Create New Agent"
                description="Add a new AI agent to your system"
                href="/admin/agents/new"
                icon="+"
              />
              <ActionCard
                title="Manage Agents"
                description="View and edit existing agents"
                href="/admin/agents"
                icon="📋"
              />
              <ActionCard
                title="Add Custom Tool"
                description="Integrate a new API tool"
                href="/admin/tools/new"
                icon="🔧"
              />
            </div>
          </div>

          {/* Agent Flow Diagram */}
          <div className="mt-10 space-y-3">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Agent Workflow
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              ภาพรวมเส้นทางโอนงาน: เริ่มจาก Coordinator แล้วส่งต่อไปยัง Agent ที่มีอยู่ในระบบ (ดึงจากฐานข้อมูล)
            </p>
            <AgentFlowGraph agents={stats.agents} />
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
    purple:
      "bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400",
    orange:
      "bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400",
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div
        className={`inline-flex items-center justify-center w-12 h-12 rounded-lg mb-4 ${
          colorClasses[color as keyof typeof colorClasses]
        }`}
      >
        <span className="text-2xl font-bold">{value}</span>
      </div>
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">
        {title}
      </h3>
      <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
        {description}
      </p>
    </div>
  );
}

function ActionCard({
  title,
  description,
  href,
  icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: string;
}) {
  return (
    <Link
      href={href}
      className="block bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
    >
      <div className="text-3xl mb-3">{icon}</div>
      <h3 className="text-base font-medium text-gray-900 dark:text-white">
        {title}
      </h3>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        {description}
      </p>
    </Link>
  );
}
