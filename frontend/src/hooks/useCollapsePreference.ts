"use client";

import { useEffect, useState } from "react";

export function useCollapsePreference() {
  // Default to collapsed = true so conversation is hidden by default
  const [collapsed, setCollapsed] = useState<boolean>(true);

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
