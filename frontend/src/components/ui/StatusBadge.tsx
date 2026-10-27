import * as React from "react";

import { Badge, type BadgeProps } from "@/components/ui/Badge";
import { cn } from "@/components/ui/utils";

/*
 * StatusBadge — render any status string as a triad badge. Unknown statuses
 * fall back to neutral, so new backend states never render unstyled.
 */
const STATUS_VARIANTS: Record<string, BadgeProps["variant"]> = {
  // health / lifecycle
  ready: "success",
  active: "success",
  running: "success",
  completed: "success",
  connected: "success",
  enabled: "success",
  live: "success",
  ok: "success",

  error: "danger",
  failed: "danger",
  inactive: "neutral",
  disabled: "neutral",
  stopped: "neutral",
  archived: "neutral",
  disconnected: "danger",

  pending: "warning",
  draft: "warning",
  paused: "warning",
  training: "info",
  processing: "info",
};

export interface StatusBadgeProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "children"> {
  /** Raw status value, e.g. "ready" | "error" | "pending" | "training" */
  status: string;
  /** Optional display label; defaults to the raw status */
  label?: React.ReactNode;
  /** Override the inferred variant for a specific status */
  variant?: BadgeProps["variant"];
  /** Optional status dot in the badge's own color */
  dot?: boolean;
}

const DOT_COLORS: Record<string, string> = {
  success: "bg-[var(--status-success)]",
  danger: "bg-[var(--status-danger)]",
  warning: "bg-[var(--status-warning)]",
  info: "bg-[var(--status-info)]",
  neutral: "bg-[var(--status-neutral)]",
};

function StatusBadge({
  status,
  label,
  variant,
  dot = false,
  className,
  ...props
}: StatusBadgeProps) {
  const resolved = variant ?? STATUS_VARIANTS[status.toLowerCase()] ?? "neutral";
  return (
    <Badge variant={resolved} className={className} {...props}>
      {dot && (
        <span
          aria-hidden
          className={cn("size-1.5 rounded-full", DOT_COLORS[resolved ?? "neutral"])}
        />
      )}
      {label ?? status}
    </Badge>
  );
}

export { StatusBadge, STATUS_VARIANTS };
