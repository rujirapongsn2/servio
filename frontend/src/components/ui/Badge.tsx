import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/components/ui/utils";

/*
 * Badge — token-driven pill. Triad variants (success/danger/warning/neutral/
 * info) use the status triads from globals.css: solid color text on a tinted
 * background with a matching tinted border. Tier variants keep the Softnix
 * product-tier accents (data / genai / agents) untouched.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium leading-4 transition-colors [&_svg]:size-3 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        neutral:
          "border-[var(--status-neutral-border)] bg-[var(--status-neutral-tint)] text-[var(--status-neutral)]",
        success:
          "border-[var(--status-success-border)] bg-[var(--status-success-tint)] text-[var(--status-success)]",
        danger:
          "border-[var(--status-danger-border)] bg-[var(--status-danger-tint)] text-[var(--status-danger)]",
        warning:
          "border-[var(--status-warning-border)] bg-[var(--status-warning-tint)] text-[var(--status-warning)]",
        info: "border-[var(--status-info-border)] bg-[var(--status-info-tint)] text-[var(--status-info)]",
        brand: "border-transparent bg-brand-tint text-brand",
        solid: "border-transparent bg-brand text-primary-foreground",
        tierData:
          "border-transparent bg-[var(--tier-data-tint)] text-[var(--tier-data)]",
        tierGenai:
          "border-transparent bg-[var(--tier-genai-tint)] text-[var(--tier-genai)]",
        tierAgents:
          "border-transparent bg-[var(--tier-agents-tint)] text-[var(--tier-agents-fg)]",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
