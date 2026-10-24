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
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
} from "lucide-react";
import { TeamProvider } from "@/lib/team-context";
import TeamSwitcher from "@/components/TeamSwitcher";

const OPERATOR_ALLOWED_PATHS = ["/admin/monitor", "/admin/account"];

function shouldShowTeamContextSwitcher(pathname: string) {
  if (pathname.startsWith("/admin/tools/channels") || pathname.startsWith("/admin/tools/widget")) {
    return false;
  }

  return (
    pathname === "/admin/tools" ||
    pathname.startsWith("/admin/tools/new") ||
    /^\/admin\/tools\/[^/]+$/.test(pathname) ||
    pathname.startsWith("/admin/monitor") ||
    pathname.startsWith("/admin/analytics") ||
    /^\/admin\/agents\/[^/]+$/.test(pathname)
  );
}

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
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const isWorkflow = /^\/admin\/teams\/\d+\/workflow$/.test(pathname);

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
    <div className="min-h-screen bg-canvas text-ink" data-viewer-only={isViewerOnly ? "1" : "0"}>
      {isWorkflow && mobileSidebarOpen && <button type="button" aria-label="Close navigation" onClick={() => setMobileSidebarOpen(false)} className="fixed inset-0 z-20 bg-slate-950/30 lg:hidden" />}
      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 ${collapsed ? "w-16" : "w-64"} border-r border-line bg-white text-ink transition-all duration-200 z-20 ${isWorkflow && !mobileSidebarOpen ? "max-lg:-translate-x-full max-lg:invisible" : ""}`}
        onClick={(event) => { if (event.target instanceof Element && event.target.closest("a")) setMobileSidebarOpen(false); }}
      >
        <div className="flex flex-col h-full">
          {/* Header with logo */}
          {/* Brand block: Servio wordmark as the product brand, "by Softnix" endorsement (EDC1 sidebar pattern) */}
          <div className={`flex min-h-14 items-center gap-2 ${collapsed ? "flex-col justify-center px-2 py-3" : "justify-between px-4 py-3"}`}>
            {collapsed ? (
              <img src="/softnix-mark.png" alt="Servio by Softnix" title="Servio by Softnix" className="h-8 w-8" />
            ) : (
              <Link href="/admin" className="min-w-0 rounded-md focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary-100" aria-label="Servio by Softnix, go to dashboard">
                <img src="/servio-wordmark.png" alt="Servio" className="block h-7 w-auto" />
                <span className="mt-1 flex items-center gap-1 text-[11px] font-medium text-ink-3">
                  by
                  <img src="/softnix-mark.png" alt="" aria-hidden="true" className="h-3.5 w-3.5" />
                  Softnix
                </span>
              </Link>
            )}
            <Button
              size="iconSmall"
              variant="ghost"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={toggleSidebar}
              className="shrink-0 text-ink-2"
            >
              {collapsed ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
            </Button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2.5 py-2 space-y-0.5 overflow-y-auto">
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
                    <span className="ml-auto inline-flex h-[18px] items-center rounded-md bg-amber-50 px-1.5 text-[11px] font-medium text-amber-700">
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
                    active={pathname.startsWith("/admin/settings") || pathname.startsWith("/admin/providers")}
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
          <div className="border-t border-line p-2.5">
            <Link
              href="/admin/account"
              className={`flex items-center gap-2.5 rounded-md p-1.5 hover:bg-hover transition-colors ${collapsed ? "justify-center" : ""}`}
              title="Account settings"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-[13px] font-semibold text-white">
                {username.charAt(0).toUpperCase()}
              </div>
              <div className={`min-w-0 truncate text-[13px] font-semibold text-ink ${collapsed ? "hidden" : "block"}`}>
                {username}
              </div>
            </Link>
            <button
              onClick={handleLogout}
              title="Logout"
              className={`mt-0.5 flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium text-ink-2 hover:bg-hover hover:text-ink transition-colors ${collapsed ? "justify-center" : ""}`}
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              <span className={collapsed ? "sr-only" : ""}>Logout</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={`${isWorkflow ? collapsed ? "ml-0 lg:ml-16 [--admin-sidebar-width:0rem] lg:[--admin-sidebar-width:4rem]" : "ml-0 lg:ml-64 [--admin-sidebar-width:0rem] lg:[--admin-sidebar-width:16rem]" : collapsed ? "ml-16" : "ml-64"} transition-all duration-200 relative z-0`}
        style={isWorkflow ? undefined : { "--admin-sidebar-width": collapsed ? "4rem" : "16rem" } as React.CSSProperties}
      >
        {/* Top bar */}
        <div className="sticky top-0 z-10 flex h-14 items-center justify-end border-b border-line bg-topbar px-4 sm:px-7">
          {isWorkflow && <button type="button" aria-label="Open navigation" aria-expanded={mobileSidebarOpen} onClick={() => setMobileSidebarOpen(true)} className="mr-auto inline-flex items-center gap-2 rounded-lg p-2 text-sm lg:hidden"><Menu className="h-5 w-5" />Navigation</button>}
          {shouldShowTeamContextSwitcher(pathname) && (
            <TeamSwitcher label="Team Agent" />
          )}
        </div>
        <main className={isWorkflow ? "p-4 sm:p-6 lg:p-7" : "px-7 pt-6 pb-20"}>{children}</main>
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
      className={`group block rounded-md px-2.5 py-[7px] text-[13.5px] transition-colors duration-150 ${active
        ? "bg-primary-50 font-semibold text-ink [&_svg]:text-primary"
        : "font-normal text-ink hover:bg-hover [&_svg]:text-gray-700"
        }`}
      aria-current={active ? "page" : undefined}
      title={label || undefined}
    >
      {collapsed ? (
        <span className="inline-flex w-full justify-center font-semibold relative">
          {Icon ? <Icon className="h-[18px] w-[18px]" aria-hidden="true" /> : label ? label.charAt(0) : "·"}
          {badge && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-amber-400" />
          )}
        </span>
      ) : (
        <span className="inline-flex items-center justify-between w-full">
          <span className="inline-flex items-center gap-2.5 whitespace-nowrap">
            {Icon && <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />}
            <span className="inline-block">{children}</span>
          </span>
          {badge}
        </span>
      )}
    </Link>
  );
}
