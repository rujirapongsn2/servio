"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { adminCopy, type AdminCopy, type AdminLocale } from "@/lib/admin-copy";

export const ADMIN_LOCALE_STORAGE_KEY = "servio-admin-locale";
export type AdminLocaleContextValue = { locale: AdminLocale; copy: AdminCopy; setLocale: (locale: AdminLocale) => void };
export const AdminLocaleContext = createContext<AdminLocaleContextValue | null>(null);

export function AdminLocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<AdminLocale>("th");
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(ADMIN_LOCALE_STORAGE_KEY);
      if (saved === "th" || saved === "en") setLocaleState(saved);
    } catch { /* Storage can be unavailable in private mode. */ }
  }, []);
  useEffect(() => {
    const previous = document.documentElement.lang;
    document.documentElement.lang = locale;
    return () => { document.documentElement.lang = previous; };
  }, [locale]);
  const setLocale = (next: AdminLocale) => {
    setLocaleState(next);
    try { window.localStorage.setItem(ADMIN_LOCALE_STORAGE_KEY, next); } catch {}
  };
  return <AdminLocaleContext.Provider value={{ locale, copy: adminCopy[locale], setLocale }}><div lang={locale}>{children}</div></AdminLocaleContext.Provider>;
}

export function useAdminLocale() {
  const context = useContext(AdminLocaleContext);
  if (!context) throw new Error("AdminLocaleProvider is required");
  return context;
}
