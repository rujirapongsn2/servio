"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/Button";

export interface WorkflowStep {
  label: string;
  href?: string;
  active?: boolean;
}

export interface WorkflowAction {
  label: string;
  onClick?: () => void;
  href?: string;
  variant?: "ghost" | "outline" | "primary";
}

interface WorkflowNavigatorProps {
  steps: WorkflowStep[];
  backLabel?: string;
  backHref?: string;
  onBack?: () => void;
  actions?: WorkflowAction[];
}

export default function WorkflowNavigator({
  steps,
  backLabel = "Back",
  backHref,
  onBack,
  actions = [],
}: WorkflowNavigatorProps) {
  const router = useRouter();

  const handleBack = () => {
    if (onBack) {
      onBack();
      return;
    }
    if (backHref) {
      router.push(backHref);
      return;
    }
    router.back();
  };

  const openAction = (action: WorkflowAction) => {
    if (action.onClick) {
      action.onClick();
      return;
    }
    if (action.href) {
      router.push(action.href);
    }
  };

  return (
    <div className="rounded-[14px] border border-[#E2E8F0] bg-white px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <Button type="button" variant="outline" size="sm" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
            {backLabel}
          </Button>
          <nav className="flex items-center gap-1 overflow-x-auto text-sm font-medium text-[#778DA9]">
            {steps.map((step, index) => (
              <div key={`${step.label}-${index}`} className="flex items-center gap-1 whitespace-nowrap">
                {step.href && !step.active ? (
                  <button
                    type="button"
                    onClick={() => router.push(step.href as string)}
                    className="font-medium text-[#2D3F55] hover:text-[#2786C2]"
                  >
                    {step.label}
                  </button>
                ) : (
                  <span className={step.active ? "font-semibold text-[#0D1B2A]" : ""}>
                    {step.label}
                  </span>
                )}
                {index < steps.length - 1 && <ChevronRight className="h-4 w-4 text-[#CBD5E1]" />}
              </div>
            ))}
          </nav>
        </div>
        {actions.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            {actions.map((action) => (
              <Button
                key={action.label}
                type="button"
                variant={action.variant || "ghost"}
                size="sm"
                onClick={() => openAction(action)}
              >
                {action.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
