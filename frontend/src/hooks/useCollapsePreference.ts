"use client";

import { useEffect, useState } from "react";

export function useCollapsePreference() {
  const [collapsed, setCollapsed] = useState<boolean>(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("collapseMessages");
      if (raw != null) {
        setCollapsed(raw === "1" || raw === "true");
      }
    } catch {}
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("collapseMessages", collapsed ? "1" : "0");
    } catch {}
  }, [collapsed]);

  const toggle = () => setCollapsed((v) => !v);

  return { collapsed, setCollapsed, toggle } as const;
}

