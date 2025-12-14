"use client";

import { useState } from "react";
import Image from "next/image";
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

      // Redirect to admin dashboard
      router.push("/admin");
    } catch (err: any) {
      setError(err.message || "An error occurred during login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid grid-cols-1 md:grid-cols-2 bg-white dark:bg-gray-900">
      {/* Left visual panel: blue background with Servio logo */}
      <div className="hidden md:flex flex-col bg-[#2563eb] text-white p-8">
        <img
          src="/servio_logo.png"
          alt="Servio"
          className="w-[160px] h-auto"
        />
      </div>

      {/* Right form panel: keep original login fields/logic */}
      <div className="flex items-center justify-center py-12 px-6">
        <div className="w-full max-w-md space-y-8">
          <div>
            <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 dark:text-white">
              Log in to Agent Management
            </h2>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              Sign in to access the admin dashboard
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleLogin}>
            <div className="flex flex-col gap-2">
              <label htmlFor="username" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                required
                className="h-12 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 placeholder-gray-400 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="password" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                required
                className="h-12 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 placeholder-gray-400 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className="w-full h-12 rounded-xl text-white bg-blue-600 hover:bg-blue-700 focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
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
