"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Activity,
  LineChart,
  Puzzle,
  Settings,
  Phone,
  Users,
  Shield,
} from "lucide-react";
import { TeamProvider } from "@/lib/team-context";
import TeamSwitcher from "@/components/TeamSwitcher";

const OPERATOR_ALLOWED_PATHS = ["/admin/monitor", "/admin/account"];

function AdminLayoutInner({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [isOperatorOnly, setIsOperatorOnly] = useState(false);
  const [isViewerOnly, setIsViewerOnly] = useState(false);
  const [canManageUsers, setCanManageUsers] = useState(false);
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
    setIsSuperAdmin(localStorage.getItem("isSuperAdmin") === "1");
    setCanManageUsers(localStorage.getItem("canManageUsers") === "1");
    const operatorOnly = localStorage.getItem("isOperatorOnly") === "1";
    const viewerOnly = localStorage.getItem("isViewerOnly") === "1";
    setIsOperatorOnly(operatorOnly);
    setIsViewerOnly(viewerOnly);
    if (operatorOnly && !OPERATOR_ALLOWED_PATHS.some((path) => pathname.startsWith(path))) {
      router.push("/admin/monitor");
      return;
    }
    setIsLoading(false);

    const refreshAccessFlags = async () => {
      try {
        const res = await fetch(`${window.location.origin}/api/admin/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = await res.json();
        const nextSuperAdmin = data.is_super_admin === true;
        const nextOperatorOnly = data.is_operator_only === true;
        const nextViewerOnly = data.is_viewer_only === true;
        const nextCanManageUsers = data.can_manage_users === true;
        setIsSuperAdmin(nextSuperAdmin);
        setIsOperatorOnly(nextOperatorOnly);
        setIsViewerOnly(nextViewerOnly);
        setCanManageUsers(nextCanManageUsers);
        localStorage.setItem("isSuperAdmin", nextSuperAdmin ? "1" : "0");
        localStorage.setItem("isOperatorOnly", nextOperatorOnly ? "1" : "0");
        localStorage.setItem("isViewerOnly", nextViewerOnly ? "1" : "0");
        localStorage.setItem("canManageUsers", nextCanManageUsers ? "1" : "0");
        if (nextOperatorOnly && !OPERATOR_ALLOWED_PATHS.some((path) => pathname.startsWith(path))) {
          router.push("/admin/monitor");
        }
      } catch {
        // Keep existing local access flags when refresh fails.
      }
    };
    refreshAccessFlags();

    // restore sidebar state
    try {
      const raw = localStorage.getItem("adminSidebarCollapsed");
      if (raw != null) setCollapsed(raw === "1" || raw === "true");
    } catch { }
  }, [pathname, router]);

  const handleLogout = () => {
    localStorage.removeItem("adminToken");
    localStorage.removeItem("adminUsername");
    localStorage.removeItem("isSuperAdmin");
    localStorage.removeItem("isOperatorOnly");
    localStorage.removeItem("isViewerOnly");
    localStorage.removeItem("canManageUsers");
    router.push("/admin/login");
  };

  useEffect(() => {
    if (!isViewerOnly) return;

    const actionPattern = /\b(add|create|save|new|delete)\b/i;

    const shouldDisable = (text: string) => actionPattern.test(text);

    const applyViewerActionLock = () => {
      const elements = document.querySelectorAll<HTMLButtonElement | HTMLAnchorElement>("button, a");
      elements.forEach((element) => {
        if ((element as HTMLElement).dataset.viewerActionBypass === "true") {
          return;
        }
        const content = [
          element.textContent || "",
          element.getAttribute("title") || "",
          element.getAttribute("aria-label") || "",
        ].join(" ");
        if (!shouldDisable(content)) return;

        if (element instanceof HTMLButtonElement) {
          element.disabled = true;
        } else {
          element.setAttribute("aria-disabled", "true");
          element.setAttribute("tabindex", "-1");
        }
        element.classList.add("opacity-50", "cursor-not-allowed", "pointer-events-none");
      });
    };

    applyViewerActionLock();
    const observer = new MutationObserver(() => applyViewerActionLock());
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [isViewerOnly, pathname]);

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
    <div className="min-h-screen bg-white text-[#0D1B2A]" data-viewer-only={isViewerOnly ? "1" : "0"}>
      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 ${collapsed ? "w-16" : "w-64"} border-r border-[#E2E8F0] bg-white text-[#0D1B2A] transition-all duration-200 z-20`}
      >
        <div className="flex flex-col h-full">
          {/* Header with logo */}
          <div className="flex items-center justify-between h-20 px-4 border-b border-[#E2E8F0]">
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
              className="border-[#E2E8F0] bg-[#F8F9FA] text-[#0D1B2A] hover:bg-white"
            >
              <span className={`transform transition-transform ${collapsed ? "rotate-180" : ""}`}>
                ›
              </span>
            </Button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {isOperatorOnly ? (
              <NavLink
                href="/admin/monitor"
                active={pathname.startsWith("/admin/monitor")}
                collapsed={collapsed}
                icon={Activity}
              >
                Online Agents
              </NavLink>
            ) : (
              <>
                <NavLink
                  href="/admin"
                  active={pathname === "/admin"}
                  collapsed={collapsed}
                  icon={LayoutDashboard}
                >
                  Dashboard
                </NavLink>
                <NavLink
                  href="/admin/teams"
                  active={pathname.startsWith("/admin/teams")}
                  collapsed={collapsed}
                  icon={Users}
                >
                  Team Agents
                </NavLink>
                <NavLink
                  href="/admin/tools/channels"
                  active={pathname.startsWith("/admin/tools/channels") || pathname.startsWith("/admin/tools/widget")}
                  collapsed={collapsed}
                  icon={Puzzle}
                >
                  Channels
                </NavLink>
                <NavLink
                  href="/admin/monitor"
                  active={pathname.startsWith("/admin/monitor")}
                  collapsed={collapsed}
                  icon={Activity}
                >
                  Online Agents
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
                  href="/admin/voip"
                  active={pathname.startsWith("/admin/voip")}
                  collapsed={collapsed}
                  icon={Phone}
                  badge={
                    <span className="ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide bg-[#F3903F] text-white">
                      Beta
                    </span>
                  }
                >
                  VoIP
                </NavLink>
                {canManageUsers && (
                  <NavLink
                    href="/admin/users"
                    active={pathname.startsWith("/admin/users")}
                    collapsed={collapsed}
                    icon={Shield}
                  >
                    Users
                  </NavLink>
                )}
                {isSuperAdmin && (
                  <NavLink
                    href="/admin/settings"
                    active={pathname.startsWith("/admin/settings")}
                    collapsed={collapsed}
                    icon={Settings}
                  >
                    Settings
                  </NavLink>
                )}
              </>
            )}
          </nav>

          {/* User info and logout */}
          <div className="p-4 border-t border-[#E2E8F0]">
            <Link
              href="/admin/account"
              className="flex items-center space-x-2 rounded-md p-1.5 -mx-1.5 hover:bg-[#F8F9FA] transition-colors"
              title="Account settings"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#F8F9FA] text-sm font-semibold text-[#0D1B2A] ring-1 ring-[#E2E8F0]">
                {username.charAt(0).toUpperCase()}
              </div>
              <div className={`text-sm font-medium text-[#2D3F55] ${collapsed ? "hidden" : "block"}`}>
                {username}
              </div>
            </Link>
            <button
              onClick={handleLogout}
              className="mt-2 w-full text-sm font-medium text-[#778DA9] hover:text-[#0D1B2A] flex items-center gap-1.5"
            >
              <span>Logout</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={`${collapsed ? "ml-16" : "ml-64"} transition-all duration-200 relative z-0`}
        style={{ "--admin-sidebar-width": collapsed ? "4rem" : "16rem" } as React.CSSProperties}
      >
        {/* Top bar with team switcher */}
        <div className="sticky top-0 z-10 flex h-16 items-center justify-end border-b border-[#E2E8F0] bg-white px-8">
          {!(pathname.startsWith("/admin/tools/channels") || pathname.startsWith("/admin/tools/widget")) && (
            <TeamSwitcher />
          )}
        </div>
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <TeamProvider>
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </TeamProvider>
  );
}

function NavLink({
  href,
  active,
  children,
  collapsed = false,
  icon: Icon,
  badge,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
  collapsed?: boolean;
  icon?: LucideIcon;
  badge?: React.ReactNode;
}) {
  const label = typeof children === "string" ? (children as string) : "";
  return (
    <Link
      href={href}
      className={`block rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${active
        ? "bg-[#F8F9FA] text-[#0D1B2A] shadow-[inset_3px_0_0_#2786C2]"
        : "text-[#2D3F55] hover:bg-[#F8F9FA] hover:text-[#0D1B2A]"
        }`}
      title={label || undefined}
    >
      {collapsed ? (
        <span className="inline-flex w-full justify-center font-semibold relative">
          {Icon ? <Icon className="h-5 w-5" aria-hidden="true" /> : label ? label.charAt(0) : "·"}
          {badge && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-[#F3903F]" />
          )}
        </span>
      ) : (
        <span className="inline-flex items-center justify-between w-full">
          <span className="inline-flex items-center space-x-3 whitespace-nowrap">
            {Icon && <Icon className="h-5 w-5" aria-hidden="true" />}
            <span className="inline-block">{children}</span>
          </span>
          {badge}
        </span>
      )}
    </Link>
  );
}
