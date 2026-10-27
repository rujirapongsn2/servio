"use client";

import { useAdminLocale } from "@/lib/admin-locale";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
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
  ChevronLeft,
} from "lucide-react";
import { AdminLocaleProvider } from "@/lib/admin-locale";
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
  const { locale, copy, setLocale } = useAdminLocale();
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
  const responsiveNavigation = isWorkflow || pathname === "/admin/settings" || pathname === "/admin/teams";

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
    const locked = new Map<HTMLElement, { disabled?: boolean; ariaDisabled: string | null; tabIndex: string | null }>();
    const lock = (element: HTMLButtonElement | HTMLAnchorElement) => {
      if (!locked.has(element)) locked.set(element, {
        disabled: element instanceof HTMLButtonElement ? element.disabled : undefined,
        ariaDisabled: element.getAttribute("aria-disabled"), tabIndex: element.getAttribute("tabindex"),
      });
      if (element instanceof HTMLButtonElement) {
        if (!element.disabled) element.disabled = true;
      } else {
        if (element.getAttribute("aria-disabled") !== "true") element.setAttribute("aria-disabled", "true");
        if (element.getAttribute("tabindex") !== "-1") element.setAttribute("tabindex", "-1");
      }
      for (const token of ["opacity-50", "cursor-not-allowed", "pointer-events-none"]) {
        if (!element.classList.contains(token)) element.classList.add(token);
      }
    };
    const unlock = (element: HTMLElement) => {
      const previous = locked.get(element);
      if (!previous) return;
      if (element instanceof HTMLButtonElement && previous.disabled !== undefined && element.disabled !== previous.disabled) element.disabled = previous.disabled;
      if (previous.ariaDisabled === null) element.removeAttribute("aria-disabled"); else element.setAttribute("aria-disabled", previous.ariaDisabled);
      if (previous.tabIndex === null) element.removeAttribute("tabindex"); else element.setAttribute("tabindex", previous.tabIndex);
      element.classList.remove("opacity-50", "cursor-not-allowed", "pointer-events-none");
      locked.delete(element);
    };
    const applyViewerActionLock = () => {
      document.querySelectorAll<HTMLButtonElement | HTMLAnchorElement>("button, a").forEach((element) => {
        const content = [element.textContent || "", element.getAttribute("title") || "", element.getAttribute("aria-label") || ""].join(" ");
        const shouldLock = element.dataset.viewerActionBypass !== "true" &&
          (element.dataset.adminWrite === "true" || actionPattern.test(content));
        if (shouldLock) lock(element); else unlock(element);
      });
    };
    applyViewerActionLock();
    const observer = new MutationObserver(applyViewerActionLock);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true,
      attributes: true, attributeFilter: ["disabled", "aria-disabled", "title", "aria-label", "data-admin-write"] });
    return () => { observer.disconnect(); for (const element of locked.keys()) unlock(element); };
  }, [isViewerOnly, pathname, locale]);

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
    <div lang={locale} className="min-h-screen bg-app text-fg" data-viewer-only={isViewerOnly ? "1" : "0"}>
      {responsiveNavigation && mobileSidebarOpen && <button type="button" aria-label={copy.closeNavigation} onClick={() => setMobileSidebarOpen(false)} className="fixed inset-0 z-20 bg-slate-950/30 lg:hidden" />}
      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 ${collapsed ? "w-16" : "w-64"} border-r border-hairline bg-app text-fg transition-all duration-200 z-20 ${responsiveNavigation && !mobileSidebarOpen ? "max-lg:-translate-x-full max-lg:invisible" : ""}`}
        onClick={(event) => { if (event.target instanceof Element && event.target.closest("a")) setMobileSidebarOpen(false); }}
      >
        <div className="flex flex-col h-full">
          {/* Header with logo */}
          <div className="flex items-center justify-between h-20 px-4 border-b border-hairline">
            <img
              src="/servio_logo.png"
              alt="Servio"
              className={`${collapsed ? "w-[40px]" : "w-[140px]"} h-auto transition-all`}
            />
            <button
              type="button"
              aria-label={collapsed ? copy.expandSidebar : copy.collapseSidebar}
              title={collapsed ? copy.expandSidebar : copy.collapseSidebar}
              onClick={toggleSidebar}
              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-fg-2 press hover:bg-hover hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <ChevronLeft className={`size-3.5 transition-transform duration-200 ease-out ${collapsed ? "rotate-180" : ""}`} aria-hidden />
              <span className="sr-only">{collapsed ? copy.expandSidebar : copy.collapseSidebar}</span>
            </button>
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
                {copy.onlineAgents}
              </NavLink>
            ) : (
              <>
                <NavLink
                  href="/admin"
                  active={pathname === "/admin"}
                  collapsed={collapsed}
                  icon={LayoutDashboard}
                >
                  {copy.dashboard}
                </NavLink>
                <NavLink
                  href="/admin/teams"
                  active={pathname.startsWith("/admin/teams")}
                  collapsed={collapsed}
                  icon={Users}
                >
                  {copy.teamAgents}
                </NavLink>
                <NavLink
                  href="/admin/tools/channels"
                  active={pathname.startsWith("/admin/tools/channels") || pathname.startsWith("/admin/tools/widget")}
                  collapsed={collapsed}
                  icon={Puzzle}
                >
                  {copy.channels}
                </NavLink>
                <NavLink
                  href="/admin/monitor"
                  active={pathname.startsWith("/admin/monitor")}
                  collapsed={collapsed}
                  icon={Activity}
                >
                  {copy.onlineAgents}
                </NavLink>
                <NavLink
                  href="/admin/analytics"
                  active={pathname.startsWith("/admin/analytics")}
                  collapsed={collapsed}
                  icon={LineChart}
                >
                  {copy.analytics}
                </NavLink>
                <NavLink
                  href="/admin/voip"
                  active={pathname.startsWith("/admin/voip")}
                  collapsed={collapsed}
                  icon={Phone}
                  badge={
                    <span className="ml-auto rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide bg-[var(--tier-genai-tint)] text-[var(--tier-genai)] border border-[var(--tier-genai-tint)]">
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
                    {copy.users}
                  </NavLink>
                )}
                {isSuperAdmin && (
                  <NavLink
                    href="/admin/settings"
                    active={pathname.startsWith("/admin/settings") || pathname.startsWith("/admin/providers")}
                    collapsed={collapsed}
                    icon={Settings}
                  >
                    {copy.settings}
                  </NavLink>
                )}
              </>
            )}
          </nav>

          {/* User info and logout */}
          <div className="p-4 border-t border-hairline">
            <Link
              href="/admin/account"
              className="flex items-center space-x-2 rounded-md p-1.5 -mx-1.5 hover:bg-hover transition-colors"
              title={copy.accountSettings}
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-hover text-sm font-semibold text-fg ring-1 ring-hairline">
                {username.charAt(0).toUpperCase()}
              </div>
              <div className={`text-sm font-medium text-charcoal ${collapsed ? "hidden" : "block"}`}>
                {username}
              </div>
            </Link>
            <button
              onClick={handleLogout}
              className="mt-2 w-full text-sm font-medium text-fg-2 hover:text-fg flex items-center gap-1.5"
            >
              <span>{copy.logout}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={`${responsiveNavigation ? collapsed ? "ml-0 lg:ml-16 [--admin-sidebar-width:0rem] lg:[--admin-sidebar-width:4rem]" : "ml-0 lg:ml-64 [--admin-sidebar-width:0rem] lg:[--admin-sidebar-width:16rem]" : collapsed ? "ml-16" : "ml-64"} transition-all duration-200 relative z-0 min-h-screen bg-app`}
        style={responsiveNavigation ? undefined : { "--admin-sidebar-width": collapsed ? "4rem" : "16rem" } as React.CSSProperties}
      >
        {/* Top bar */}
        <div className="sticky top-0 z-10 flex h-16 items-center justify-end border-b border-hairline bg-app px-4 sm:px-8">
          {responsiveNavigation && <button type="button" aria-label={copy.openNavigation} aria-expanded={mobileSidebarOpen} onClick={() => setMobileSidebarOpen(true)} className="mr-auto inline-flex items-center gap-2 rounded-lg p-2 text-sm lg:hidden"><Menu className="h-5 w-5" />{copy.navigation}</button>}
          <label className="mr-3 flex items-center gap-2 text-xs font-medium text-fg-2">
            <span className="sr-only sm:not-sr-only">{copy.language}</span>
            <select aria-label={copy.language} value={locale} onChange={(event) => setLocale(event.target.value === "en" ? "en" : "th")} className="rounded-md border border-control bg-surface px-2 py-1.5 text-sm text-fg">
              <option value="th">ไทย</option><option value="en">EN</option>
            </select>
          </label>
          {shouldShowTeamContextSwitcher(pathname) && (
            <TeamSwitcher label={copy.teamAgent} />
          )}
        </div>
        <main className={responsiveNavigation ? "p-4 sm:p-6 lg:p-8" : "p-8"}>{children}</main>
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
    <AdminLocaleProvider>
      <TeamProvider>
        <AdminLayoutInner>{children}</AdminLayoutInner>
      </TeamProvider>
    </AdminLocaleProvider>
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
      className={`block rounded-lg px-3 py-2 text-sm font-medium press ${active
        ? "bg-selected text-fg shadow-[inset_3px_0_0_var(--brand)]"
        : "text-charcoal hover:bg-hover hover:text-fg"
        }`}
      title={label || undefined}
    >
      {collapsed ? (
        <span className="inline-flex w-full justify-center font-semibold relative">
          {Icon ? <Icon className="h-5 w-5" aria-hidden="true" /> : label ? label.charAt(0) : "·"}
          {badge && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-[var(--tier-genai)]" />
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
