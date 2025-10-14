"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [username, setUsername] = useState("");

  useEffect(() => {
    // Skip auth check for login page
    if (pathname === "/admin/login") {
      setIsLoading(false);
      return;
    }

    // Check if token exists
    const token = localStorage.getItem("adminToken");
    const storedUsername = localStorage.getItem("adminUsername");

    if (!token) {
      router.push("/admin/login");
      return;
    }

    setIsAuthenticated(true);
    setUsername(storedUsername || "Admin");
    setIsLoading(false);
  }, [pathname, router]);

  const handleLogout = () => {
    localStorage.removeItem("adminToken");
    localStorage.removeItem("adminUsername");
    router.push("/admin/login");
  };

  // Show loading or login page without layout
  if (isLoading || pathname === "/admin/login") {
    return children;
  }

  // Show protected content with sidebar layout
  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">
              Admin Panel
            </h1>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
            <NavLink href="/admin" active={pathname === "/admin"}>
              Dashboard
            </NavLink>
            <NavLink
              href="/admin/agents"
              active={pathname.startsWith("/admin/agents")}
            >
              Agents
            </NavLink>
            <NavLink
              href="/admin/tools"
              active={pathname.startsWith("/admin/tools")}
            >
              Tools
            </NavLink>
            <NavLink
              href="/admin/settings"
              active={pathname.startsWith("/admin/settings")}
            >
              Settings
            </NavLink>
          </nav>

          {/* User info and logout */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white font-semibold">
                  {username.charAt(0).toUpperCase()}
                </div>
                <div className="text-sm text-gray-900 dark:text-white">
                  {username}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="ml-64">
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`block px-3 py-2 rounded-md text-sm font-medium ${
        active
          ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400"
          : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
      }`}
    >
      {children}
    </Link>
  );
}
