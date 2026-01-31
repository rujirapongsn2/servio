"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";


interface IntentRule {
  id: number;
  group: string;
  keywords: string[];
  color: string;
  description: string;
}

function IntentRulesSection({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [rules, setRules] = useState<IntentRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editKeywords, setEditKeywords] = useState("");
  const [msg, setMsg] = useState("");

  const fetchRules = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const res = await fetch(`${apiBaseUrl}/api/admin/intent-rules`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setRules(data);
        return data;
      }
    } catch (e) {
      console.error("Failed to fetch intent rules", e);
    }
    return [];
  };

  const initDefaultRules = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const res = await fetch(`${apiBaseUrl}/api/admin/intent-rules/init-defaults`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        await fetchRules();
      }
    } catch (e) {
      console.error("Failed to init default rules", e);
    }
  };

  useEffect(() => {
    fetchRules().then((data) => {
      // Auto-initialize default rules if none exist
      if (data && data.length === 0) {
        initDefaultRules();
      }
    });
  }, []);

  const handleSave = async (id: number) => {
    setLoading(true);
    setMsg("");
    try {
      const token = localStorage.getItem("adminToken");
      const keywordsArray = editKeywords.split(",").map(k => k.trim()).filter(Boolean);

      const res = await fetch(`${apiBaseUrl}/api/admin/intent-rules/${id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ keywords: keywordsArray })
      });

      if (res.ok) {
        await fetchRules();
        setEditingId(null);
        setMsg("Saved successfully");
      } else {
        setMsg("Failed to save");
      }
    } catch (e) {
      setMsg("Error saving");
    } finally {
      setLoading(false);
      setTimeout(() => setMsg(""), 3000);
    }
  };

  const handleDelete = async (id: number, groupName: string) => {
    if (!confirm(`Are you sure you want to delete the rule for "${groupName}"?`)) {
      return;
    }

    setLoading(true);
    setMsg("");
    try {
      const token = localStorage.getItem("adminToken");
      const res = await fetch(`${apiBaseUrl}/api/admin/intent-rules/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });

      if (res.ok) {
        await fetchRules();
        setMsg("Rule deleted successfully");
      } else {
        setMsg("Failed to delete rule");
      }
    } catch (e) {
      setMsg("Error deleting rule");
    } finally {
      setLoading(false);
      setTimeout(() => setMsg(""), 3000);
    }
  };

  const startEdit = (rule: IntentRule) => {
    setEditingId(rule.id);
    setEditKeywords(rule.keywords.join(", "));
  };

  return (
    <div className="mb-8">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-md font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <span>🎯 Intent Detection Rules</span>
          {msg && <span className="text-xs text-green-500 font-normal">{msg}</span>}
        </h3>
      </div>

      <div className="space-y-3">
        {rules.length === 0 && (
          <div className="text-sm text-gray-500 text-center py-4 border border-dashed rounded-lg">
            No rules found. Initializing default rules...
          </div>
        )}
        {rules.map(rule => (
          <div key={rule.id} className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-start mb-2">
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: rule.color }}
                />
                <span className="font-medium text-sm text-gray-900 dark:text-white">
                  {rule.group}
                </span>
              </div>
              {editingId === rule.id ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => handleSave(rule.id)}
                    disabled={loading}
                    className="text-xs text-green-600 hover:text-green-700 font-medium"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditingId(null)}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => startEdit(rule)}
                    className="text-xs text-blue-600 hover:text-blue-700"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(rule.id, rule.group)}
                    disabled={loading}
                    className="text-xs text-red-600 hover:text-red-700"
                  >
                    Delete
                  </button>
                </div>
              )}
            </div>

            {editingId === rule.id ? (
              <div className="space-y-1">
                <textarea
                  value={editKeywords}
                  onChange={(e) => setEditKeywords(e.target.value)}
                  className="w-full text-sm px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800"
                  placeholder="e.g. refund, lawyer, urgent"
                  rows={2}
                />
                <p className="text-[10px] text-gray-500">Separate keywords with commas</p>
              </div>
            ) : (
              <div className="text-sm text-gray-600 dark:text-gray-400 break-words">
                {rule.keywords && rule.keywords.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {rule.keywords.map((k, i) => (
                      <span key={i} className="inline-block px-1.5 py-0.5 bg-gray-200 dark:bg-gray-700 rounded text-xs">
                        {k}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="italic text-gray-400">No manual keywords defined (AI only)</span>
                )}
              </div>
            )}
            {rule.description && (
              <p className="mt-1 text-[10px] text-gray-400">{rule.description}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const apiBaseUrl = getApiBaseUrl();
  const [activeTab, setActiveTab] = useState<"general" | "intent-rules">("general");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [sys, setSys] = useState<any>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteSuccess, setDeleteSuccess] = useState("");

  useEffect(() => {
    const fetchInfo = async () => {
      try {
        const token = localStorage.getItem("adminToken");
        const res = await fetch(`${apiBaseUrl}/api/admin/system-info`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setSys(data);
        }
      } catch (e) {
        // silent
      }
    };
    fetchInfo();
  }, []);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    // Validation
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }

    if (newPassword.length < 6) {
      setError("New password must be at least 6 characters long");
      return;
    }

    setLoading(true);

    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(
        `${apiBaseUrl}/api/admin/auth/change-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Failed to change password");
      }

      setSuccess("Password changed successfully!");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err.message || "An error occurred while changing password");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteHistory = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeleteError("");
    setDeleteSuccess("");

    if (deleteConfirm.trim().toUpperCase() !== "DELETE") {
      setDeleteError('กรุณาพิมพ์ "DELETE" เพื่อยืนยันการลบประวัติการสนทนา');
      return;
    }

    setDeleteLoading(true);
    try {
      const token = localStorage.getItem("adminToken");
      const res = await fetch(`${apiBaseUrl}/api/admin/conversations`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "ลบประวัติการสนทนาไม่สำเร็จ");
      }

      const data = await res.json().catch(() => ({}));
      setDeleteSuccess(
        data?.message || "ลบประวัติการสนทนาทั้งหมดเรียบร้อยแล้ว"
      );
      setDeleteConfirm("");
    } catch (err: any) {
      setDeleteError(err.message || "เกิดข้อผิดพลาดขณะลบประวัติการสนทนา");
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
          Settings
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Manage your system and admin account
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab("general")}
            className={`
              py-4 px-1 border-b-2 font-medium text-sm transition-colors
              ${activeTab === "general"
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300"}
            `}
          >
            General
          </button>
          <button
            onClick={() => setActiveTab("intent-rules")}
            className={`
              py-4 px-1 border-b-2 font-medium text-sm transition-colors
              ${activeTab === "intent-rules"
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300"}
            `}
          >
            Intent Detection Rules
          </button>
        </nav>
      </div>

      <div className="mt-6">
        {activeTab === "general" ? (
          <div className="space-y-6">
            {/* Change Password Section */}
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                Change Password
              </h2>

              <form onSubmit={handleChangePassword} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Current Password
                  </label>
                  <input
                    type="password"
                    required
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    New Password
                  </label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Confirm New Password
                  </label>
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
                  />
                </div>

                {error && (
                  <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
                    <div className="text-sm text-red-800 dark:text-red-300">
                      {error}
                    </div>
                  </div>
                )}

                {success && (
                  <div className="rounded-md bg-green-50 dark:bg-green-900/20 p-4">
                    <div className="text-sm text-green-800 dark:text-green-300">
                      {success}
                    </div>
                  </div>
                )}

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={loading}
                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                  >
                    {loading ? "Changing Password..." : "Change Password"}
                  </button>
                </div>
              </form>
            </div>

            {/* Delete Conversation History */}
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-red-200 dark:border-red-800 p-6">
              <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                ลบประวัติการสนทนา
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                การลบนี้จะลบข้อมูลการสนทนา ข้อความ และสถิติทั้งหมดออกจากระบบ ไม่สามารถกู้คืนได้
              </p>
              <form onSubmit={handleDeleteHistory} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    พิมพ์ <span className="font-mono">DELETE</span> เพื่อยืนยัน
                  </label>
                  <input
                    type="text"
                    value={deleteConfirm}
                    onChange={(e) => setDeleteConfirm(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 dark:bg-gray-900 dark:text-white"
                    placeholder="DELETE"
                  />
                </div>

                {deleteError && (
                  <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
                    <div className="text-sm text-red-800 dark:text-red-300">
                      {deleteError}
                    </div>
                  </div>
                )}

                {deleteSuccess && (
                  <div className="rounded-md bg-green-50 dark:bg-green-900/20 p-4">
                    <div className="text-sm text-green-800 dark:text-green-300">
                      {deleteSuccess}
                    </div>
                  </div>
                )}

                <div className="pt-2 flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={deleteLoading}
                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
                  >
                    {deleteLoading ? "กำลังลบ..." : "ลบประวัติการสนทนาทั้งหมด"}
                  </button>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    การกระทำนี้ไม่สามารถย้อนกลับได้
                  </span>
                </div>
              </form>
            </div>

            {/* System Information */}
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
              <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                System Information
              </h2>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Backend API:</span>
                  <span className="text-gray-900 dark:text-white font-mono">
                    {sys?.backend_url || apiBaseUrl}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Frontend:</span>
                  <span className="text-gray-900 dark:text-white font-mono">
                    {sys?.frontend_origin || (typeof window !== 'undefined' ? window.location.origin : '')}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Server Time (UTC):</span>
                  <span className="text-gray-900 dark:text-white font-mono">
                    {sys?.server_time || "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Python:</span>
                  <span className="text-gray-900 dark:text-white font-mono">
                    {sys?.python_version || "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">MCP Enabled:</span>
                  <span className="text-gray-900 dark:text-white">
                    {sys?.mcp_enabled ? "Yes" : "No"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">OpenAI Key Set:</span>
                  <span className="text-gray-900 dark:text-white">
                    {sys?.openai_api_key_set ? "Yes" : "No"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Agents / Tools:</span>
                  <span className="text-gray-900 dark:text-white">
                    {sys ? `${sys.agents_count} / ${sys.tools_count}` : "-"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Username:</span>
                  <span className="text-gray-900 dark:text-white">
                    {typeof window !== "undefined" && localStorage.getItem("adminUsername")}
                  </span>
                </div>
              </div>
            </div>

            {/* Default Credentials Info */}
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
              <h3 className="text-sm font-medium text-yellow-900 dark:text-yellow-300 mb-2">
                Default Login Credentials
              </h3>
              <div className="text-sm text-yellow-800 dark:text-yellow-400 space-y-1">
                <p>• Username: <span className="font-mono">admin</span></p>
                <p>• Password: <span className="font-mono">admin123</span></p>
                <p className="mt-2 text-xs">
                  For security, please change the default password immediately.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-6">
              Intent Detection Configuration
            </h2>
            <IntentRulesSection apiBaseUrl={apiBaseUrl} />
          </div>
        )}
      </div>
    </div>
  );
}
