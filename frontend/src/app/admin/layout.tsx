"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Bot,
  Activity,
  LineChart,
  Wrench,
  Puzzle,
  Settings,
} from "lucide-react";

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
  const [collapsed, setCollapsed] = useState(false);

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

    // restore sidebar state
    try {
      const raw = localStorage.getItem("adminSidebarCollapsed");
      if (raw != null) setCollapsed(raw === "1" || raw === "true");
    } catch { }
  }, [pathname, router]);

  const handleLogout = () => {
    localStorage.removeItem("adminToken");
    localStorage.removeItem("adminUsername");
    router.push("/admin/login");
  };

  const toggleSidebar = () => {
    setCollapsed((v) => {
      const nv = !v;
      try {
        localStorage.setItem("adminSidebarCollapsed", nv ? "1" : "0");
      } catch { }
      return nv;
    });
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
      {/* Sidebar (Brand Blue #2786C2) */}
      <div
        className={`fixed inset-y-0 left-0 ${collapsed ? "w-16" : "w-64"} bg-[#2786C2] text-white border-r border-[#1e6b9d] transition-all duration-200 z-20 shadow-xl`}
      >
        <div className="flex flex-col h-full">
          {/* Header with logo */}
          <div className="flex items-center justify-between h-20 px-4 border-none">
            <img
              src="/servio_logo.png"
              alt="Servio"
              className={`${collapsed ? "w-[40px]" : "w-[140px]"} h-auto transition-all`}
            />
            <Button
              size="iconSmall"
              variant="outline"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={toggleSidebar}
              className="bg-white/10 border-white/20 text-white hover:bg-white/20"
            >
              <span className={`transform transition-transform ${collapsed ? "rotate-180" : ""}`}>
                ›
              </span>
            </Button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
            <NavLink
              href="/admin"
              active={pathname === "/admin"}
              collapsed={collapsed}
              icon={LayoutDashboard}
            >
              Dashboard
            </NavLink>
            <NavLink
              href="/admin/agents"
              active={pathname.startsWith("/admin/agents")}
              collapsed={collapsed}
              icon={Bot}
            >
              Manage Agents
            </NavLink>
            <NavLink
              href="/admin/monitor"
              active={pathname.startsWith("/admin/monitor")}
              collapsed={collapsed}
              icon={Activity}
            >
              Online Agent
            </NavLink>
            <NavLink
              href="/admin/analytics"
              active={pathname.startsWith("/admin/analytics")}
              collapsed={collapsed}
              icon={LineChart}
            >
              Analytics
            </NavLink>
            <NavLink
              href="/admin/tools"
              active={pathname === "/admin/tools"}
              collapsed={collapsed}
              icon={Wrench}
            >
              Tools
            </NavLink>
            <NavLink
              href="/admin/tools/widget"
              active={pathname.startsWith("/admin/tools/widget")}
              collapsed={collapsed}
              icon={Puzzle}
            >
              Widget
            </NavLink>
            <NavLink
              href="/admin/settings"
              active={pathname.startsWith("/admin/settings")}
              collapsed={collapsed}
              icon={Settings}
            >
              Settings
            </NavLink>
          </nav>

          {/* User info and logout */}
          <div className="p-4 border-none">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 bg-gradient-to-r from-brand-start to-brand-end text-brand-dark rounded-full flex items-center justify-center font-semibold">
                  {username.charAt(0).toUpperCase()}
                </div>
                <div className={`text-sm text-white ${collapsed ? "hidden" : "block"}`}>
                  {username}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="text-sm text-white/80 hover:text-white"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className={`${collapsed ? "ml-16" : "ml-64"} transition-all duration-200 relative z-0`}>
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
  collapsed = false,
  icon: Icon,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
  collapsed?: boolean;
  icon?: LucideIcon;
}) {
  const label = typeof children === "string" ? (children as string) : "";
  return (
    <Link
      href={href}
      className={`block px-3 py-2 rounded-md text-sm font-medium transition-all duration-200 ${active
        ? "bg-gradient-to-r from-brand-start to-brand-end text-brand-dark shadow-md"
        : "text-white/80 hover:bg-white/5 hover:text-white"
        }`}
      title={label || undefined}
    >
      {collapsed ? (
        <span className="inline-flex w-full justify-center font-semibold">
          {Icon ? <Icon className="h-5 w-5" aria-hidden="true" /> : label ? label.charAt(0) : "·"}
        </span>
      ) : (
        <span className="inline-flex items-center space-x-3 whitespace-nowrap">
          {Icon && <Icon className="h-5 w-5" aria-hidden="true" />}
          <span className="inline-block">{children}</span>
        </span>
      )}
    </Link>
  );
}
