import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/components/ui/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0D1B2A] focus-visible:ring-offset-2 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        ghost:
          "text-[#2D3F55] disabled:text-[#CBD5E1] hover:bg-[#F8F9FA] hover:text-[#0D1B2A] dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white dark:disabled:text-gray-600",
        primary: "bg-[#2786C2] text-white hover:bg-[#1A5A8A] disabled:opacity-50 disabled:cursor-not-allowed",
        outline:
          "border border-[#E2E8F0] text-[#0D1B2A] bg-white hover:bg-[#F8F9FA] hover:border-[#CBD5E1] dark:border-gray-600 dark:text-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 dark:hover:border-gray-500",
        stop: "bg-red-500 text-white shadow-sm hover:bg-red-600 hover:shadow-md disabled:bg-red-300 dark:bg-red-600 dark:hover:bg-red-700 dark:disabled:bg-red-900",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-8 text-base",
        icon: "h-10 w-10 rounded-full [&_svg]:size-5",
        iconSmall: "h-8 w-8 rounded-full [&_svg]:size-4",
        iconTiny: "h-6 w-6 rounded-full [&_svg]:size-3",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
  VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
