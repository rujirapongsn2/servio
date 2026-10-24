"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { buildApiUrl } from "@/lib/api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch(buildApiUrl("/api/admin/auth/login"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "Login failed");
      }

      const data = await response.json();

      // Store token in localStorage
      localStorage.setItem("adminToken", data.access_token);
      localStorage.setItem("adminUsername", data.username);
      localStorage.setItem("isSuperAdmin", data.is_super_admin ? "1" : "0");
      localStorage.setItem("isOperatorOnly", data.is_operator_only ? "1" : "0");
      localStorage.setItem("isViewerOnly", data.is_viewer_only ? "1" : "0");
      localStorage.setItem("canManageUsers", data.can_manage_users ? "1" : "0");

      // Redirect to admin dashboard
      router.push("/admin");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "An error occurred during login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-white dark:bg-gray-900">
      {/* Left brand panel: Softnix logo + product name, flat Lakehouse canvas */}
      <div className="hidden md:flex flex-col justify-between border-r border-line bg-canvas p-8">
        <div className="leading-tight">
          <img src="/softnix-logo-color.png" alt="Softnix" className="mb-1.5 block h-9 w-auto" />
          <span className="block text-[15px] font-bold tracking-[-0.01em] text-ink">Servio</span>
        </div>
        <img src="/servio_logo.png" alt="Servio" className="mx-auto w-[240px] h-auto" />
        <span aria-hidden="true" />
      </div>

      {/* Right form panel: keep original login fields/logic */}
      <div className="flex items-center justify-center py-12 px-6">
        <div className="w-full max-w-sm space-y-7">
          <div>
            <h2 className="text-[26px] font-bold leading-tight tracking-[-0.02em] text-gray-900 dark:text-white">
              Log in to Agent Management
            </h2>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Sign in to access the admin dashboard
            </p>
          </div>

          <form className="space-y-4" onSubmit={handleLogin}>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="username" className="text-[13px] font-medium text-gray-600 dark:text-gray-300">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                className="h-10 rounded-md border border-line-strong dark:border-gray-700 bg-white dark:bg-gray-800 px-3 text-sm placeholder-gray-500 text-gray-900 dark:text-white focus:outline-none focus:border-primary focus:ring-[3px] focus:ring-primary-50"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-[13px] font-medium text-gray-600 dark:text-gray-300">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                className="h-10 rounded-md border border-line-strong dark:border-gray-700 bg-white dark:bg-gray-800 px-3 text-sm placeholder-gray-500 text-gray-900 dark:text-white focus:outline-none focus:border-primary focus:ring-[3px] focus:ring-primary-50"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
                <div className="text-sm text-red-800 dark:text-red-300">{error}</div>
              </div>
            )}

            <div>
              <Button
                type="submit"
                disabled={loading}
                className="w-full h-10 text-sm"
              >
                {loading ? "Signing in..." : "Sign In"}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
