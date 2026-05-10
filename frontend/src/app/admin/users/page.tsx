"use client";

import { useEffect, useState } from "react";
import { getApiBaseUrl } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Plus, Trash2, Shield, User, KeyRound } from "lucide-react";

interface TeamMembership {
  team_id: number;
  team_name: string;
  role: string;
}

interface AdminUser {
  id: number;
  username: string;
  created_at: string;
  teams: TeamMembership[];
}

interface TeamOption {
  id: number;
  name: string;
}

const ROLE_OPTIONS = ["owner", "admin", "operator", "viewer"] as const;

export default function UsersPage() {
  const apiBase = getApiBaseUrl();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [teams, setTeams] = useState<TeamOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [roleModalUser, setRoleModalUser] = useState<AdminUser | null>(null);
  const [roleDrafts, setRoleDrafts] = useState<Record<number, string | null>>({});
  const [savingRoles, setSavingRoles] = useState(false);
  const [roleSaveMessage, setRoleSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [pageMessage, setPageMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [passwordModalUser, setPasswordModalUser] = useState<AdminUser | null>(null);
  const [passwordInput, setPasswordInput] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [canManageUsers, setCanManageUsers] = useState(false);

  const token = typeof window !== "undefined" ? localStorage.getItem("adminToken") : "";

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${apiBase}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setUsers(await res.json());
    } catch (e) {
      console.error("Failed to fetch users", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchTeams = async () => {
    try {
      const res = await fetch(`${apiBase}/api/admin/team-agents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTeams(data.map((team: { id: number; name: string }) => ({ id: team.id, name: team.name })));
      }
    } catch (e) {
      console.error("Failed to fetch teams", e);
    }
  };

  useEffect(() => {
    setIsSuperAdmin(localStorage.getItem("isSuperAdmin") === "1");
    setCanManageUsers(localStorage.getItem("canManageUsers") === "1");
    fetchUsers();
    fetchTeams();
  }, []);

  const openPasswordModal = (user: AdminUser) => {
    setPasswordModalUser(user);
    setPasswordInput("");
    setPasswordConfirm("");
    setPasswordError("");
    setPageMessage(null);
  };

  const handleSetPassword = async () => {
    if (!passwordModalUser) return;
    if (!passwordInput.trim()) {
      setPasswordError("Password is required");
      return;
    }
    if (passwordInput !== passwordConfirm) {
      setPasswordError("Passwords do not match");
      return;
    }
    setPasswordSaving(true);
    setPasswordError("");
    try {
      const res = await fetch(`${apiBase}/api/admin/users/${passwordModalUser.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ password: passwordInput }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to update password");
      }
      setPasswordModalUser(null);
      setPageMessage({ type: "success", text: `Password updated for "${passwordModalUser.username}".` });
    } catch (e) {
      setPasswordError(e instanceof Error ? e.message : "Failed to update password");
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!newUsername || !newPassword) return;
    const res = await fetch(`${apiBase}/api/admin/users`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ username: newUsername, password: newPassword }),
    });
    if (res.ok) {
      setShowCreate(false);
      setNewUsername("");
      setNewPassword("");
      fetchUsers();
    } else {
      const data = await res.json().catch(() => ({}));
      setError(data.detail || "Failed to create user");
    }
  };

  const handleDelete = async (userId: number) => {
    if (!confirm("Delete this user?")) return;
    const res = await fetch(`${apiBase}/api/admin/users/${userId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setPageMessage({ type: "success", text: "User deleted." });
      fetchUsers();
      return;
    }
    const data = await res.json().catch(() => ({}));
    setPageMessage({ type: "error", text: data.detail || "Failed to delete user" });
  };

  const roleBadge = (role: string) => {
    const colors: Record<string, string> = {
      owner: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      admin: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
      operator: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
      viewer: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
    };
    return colors[role] || colors.viewer;
  };

  const openRoleModal = (user: AdminUser) => {
    const initialDrafts: Record<number, string | null> = {};
    teams.forEach((team) => {
      const membership = user.teams.find((t) => t.team_id === team.id);
      initialDrafts[team.id] = membership?.role ?? null;
    });
    setRoleDrafts(initialDrafts);
    setRoleSaveMessage(null);
    setPageMessage(null);
    setRoleModalUser(user);
  };

  const handleSaveRoles = async () => {
    if (!roleModalUser) return;
    setRoleSaveMessage(null);

    for (const team of teams) {
      const currentOwners = users.filter((user) =>
        user.teams.some((membership) => membership.team_id === team.id && membership.role === "owner"),
      ).length;
      const existingRole = roleModalUser.teams.find((membership) => membership.team_id === team.id)?.role ?? null;
      const nextRole = roleDrafts[team.id] ?? null;
      const ownersAfterSave =
        currentOwners - (existingRole === "owner" ? 1 : 0) + (nextRole === "owner" ? 1 : 0);
      if (ownersAfterSave < 1) {
        setRoleSaveMessage({
          type: "error",
          text: `Team "${team.name}" must have at least one owner.`,
        });
        setPageMessage(null);
        return;
      }
    }

    setSavingRoles(true);
    try {
      const responses = await Promise.all(
        teams.map((team) =>
          fetch(`${apiBase}/api/admin/team-agents/${team.id}/users`, {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              users: [
                {
                  admin_id: roleModalUser.id,
                  role: roleDrafts[team.id] ?? null,
                },
              ],
            }),
          }),
        ),
      );
      const failedResponse = responses.find((response) => !response.ok);
      if (failedResponse) {
        const error = await failedResponse.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to update some team roles");
      }
      setRoleModalUser(null);
      await fetchUsers();
      setRoleSaveMessage(null);
      setPageMessage({ type: "success", text: "Roles updated successfully." });
    } catch (e) {
      console.error("Failed to update user roles", e);
      const text = e instanceof Error ? e.message : "Failed to update user roles";
      setRoleSaveMessage({ type: "error", text });
      setPageMessage(null);
    } finally {
      setSavingRoles(false);
    }
  };

  if (loading) return <div className="text-gray-600 dark:text-gray-400">Loading users...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Users</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Manage admin users and team access</p>
        </div>
        {isSuperAdmin && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-1" /> New User
          </Button>
        )}
      </div>

      {pageMessage && (
        <div
          className={`rounded-md border px-3 py-2 text-sm ${
            pageMessage.type === "success"
              ? "border-green-200 bg-green-50 text-green-700 dark:border-green-900/40 dark:bg-green-900/20 dark:text-green-300"
              : "border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
          }`}
        >
          {pageMessage.text}
        </div>
      )}

      {/* Users Table */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">User</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Teams</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/50">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
                      <User className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <div className="font-medium text-gray-900 dark:text-white">{user.username}</div>
                      <div className="text-xs text-gray-500">Created {new Date(user.created_at).toLocaleDateString()}</div>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex flex-wrap gap-1">
                    {user.teams.length === 0 ? (
                      <span className="text-xs text-gray-400">No teams</span>
                    ) : (
                      user.teams.map((t) => (
                        <span
                          key={t.team_id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                        >
                          {t.team_name}
                          <span className={`px-1 py-0 text-[10px] rounded-full ${roleBadge(t.role)}`}>
                            {t.role}
                          </span>
                        </span>
                      ))
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    {(() => {
                      const isDefaultAdmin = user.username === "admin";
                      return (
                        <>
                    <Button variant="outline" size="sm" onClick={() => openRoleModal(user)}>
                      <Shield className="h-4 w-4 mr-1" /> Manage Roles
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openPasswordModal(user)}>
                      <KeyRound className="h-4 w-4 mr-1" /> Set Password
                    </Button>
                    {canManageUsers && (
                      <button
                        onClick={() => !isDefaultAdmin && handleDelete(user.id)}
                        disabled={isDefaultAdmin}
                        className={`p-1.5 rounded-md ${
                          isDefaultAdmin
                            ? "cursor-not-allowed text-gray-300 dark:text-gray-600"
                            : "text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20"
                        }`}
                        title={isDefaultAdmin ? "Default admin user cannot be deleted" : "Delete user"}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                        </>
                      );
                    })()}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">No users found</div>
        )}
      </div>

      {/* Create User Modal */}
      {showCreate && isSuperAdmin && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">Create User</h2>
            {error && <p className="text-sm text-red-600 mb-3">{error}</p>}
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Username</label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => { setShowCreate(false); setError(""); }}>
                Cancel
              </Button>
              <Button onClick={handleCreate} disabled={!newUsername || !newPassword}>
                Create
              </Button>
            </div>
          </div>
        </div>
      )}

      {passwordModalUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md shadow-xl">
            <h2 className="text-lg font-semibold mb-1 text-gray-900 dark:text-white">
              Set Password: {passwordModalUser.username}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              This will replace the current password for this user.
            </p>
            {passwordError && <p className="text-sm text-red-600 mb-3">{passwordError}</p>}
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">New Password</label>
                <input
                  type="password"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Confirm Password</label>
                <input
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="outline" onClick={() => setPasswordModalUser(null)}>
                Cancel
              </Button>
              <Button onClick={handleSetPassword} disabled={passwordSaving}>
                {passwordSaving ? "Saving..." : "Save Password"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {roleModalUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-2xl shadow-xl">
            <h2 className="text-lg font-semibold mb-1 text-gray-900 dark:text-white">
              Manage Roles: {roleModalUser.username}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
              Assign role per team. Select &quot;No access&quot; to remove access from that team.
            </p>

            <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
              {teams.map((team) => (
                <div
                  key={team.id}
                  className="flex items-center justify-between rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2"
                >
                  <div className="font-medium text-gray-900 dark:text-white">{team.name}</div>
                  <select
                    value={roleDrafts[team.id] ?? ""}
                    onChange={(e) =>
                      setRoleDrafts((prev) => ({
                        ...prev,
                        [team.id]: e.target.value || null,
                      }))
                    }
                    className="min-w-[160px] px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-white"
                  >
                    <option value="">No access</option>
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              {teams.length === 0 && (
                <div className="text-sm text-gray-500 dark:text-gray-400">No teams available</div>
              )}
            </div>

            {roleSaveMessage && (
              <p
                className={`mt-3 text-sm ${
                  roleSaveMessage.type === "success"
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400"
                }`}
              >
                {roleSaveMessage.text}
              </p>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <Button
                variant="outline"
                onClick={() => {
                  setRoleModalUser(null);
                  setRoleSaveMessage(null);
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleSaveRoles} disabled={savingRoles}>
                {savingRoles ? "Saving..." : "Save Roles"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
