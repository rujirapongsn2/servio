"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { getApiBaseUrl } from "@/lib/api";

export default function AccountPage() {
  const router = useRouter();
  const apiBase = getApiBaseUrl();
  const [username, setUsername] = useState("");
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setUsername(localStorage.getItem("adminUsername") || "");
    setIsSuperAdmin(localStorage.getItem("isSuperAdmin") === "1");
  }, []);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");

    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }
    if (newPassword.length < 6) {
      setError("New password must be at least 6 characters");
      return;
    }

    setSaving(true);
    try {
      const token = localStorage.getItem("adminToken");
      const res = await fetch(`${apiBase}/api/admin/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to change password");
      }

      setMessage("Password changed successfully");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setError(err.message || "Failed to change password");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div>
        <h1 className="text-[26px] font-bold leading-tight tracking-[-0.02em] text-ink">Account</h1>
        <p className="mt-1 text-base font-medium text-ink-3">
          Manage your account settings
        </p>
      </div>

      {/* Profile Info */}
      <div className="rounded-[14px] border border-line bg-white p-6">
        <h2 className="text-base font-semibold text-ink">Profile</h2>
        <div className="mt-3 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-ink-3">Username</span>
            <span className="font-medium text-ink">{username}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-3">Role</span>
            <span className={`font-medium ${isSuperAdmin ? "text-primary" : "text-ink-2"}`}>
              {isSuperAdmin ? "Administrator" : "User"}
            </span>
          </div>
        </div>
      </div>

      {/* Change Password */}
      <div className="rounded-[14px] border border-line bg-white p-6">
        <h2 className="text-base font-semibold text-ink">Change Password</h2>
        <form onSubmit={handleChangePassword} className="mt-4 space-y-4">
          {message && (
            <div className="rounded-lg bg-green-50 px-4 py-3 text-sm font-medium text-green-700">
              {message}
            </div>
          )}
          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
              {error}
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-ink-2 mb-1">
              Current Password
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-line px-4 py-3 text-sm font-medium text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink-2 mb-1">
              New Password
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
              className="w-full rounded-lg border border-line px-4 py-3 text-sm font-medium text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-ink-2 mb-1">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full rounded-lg border border-line px-4 py-3 text-sm font-medium text-ink outline-none focus:border-ink focus:ring-2 focus:ring-ink"
            />
          </div>
          <Button type="submit" disabled={saving}>
            {saving ? "Changing..." : "Change Password"}
          </Button>
        </form>
      </div>
    </div>
  );
}
