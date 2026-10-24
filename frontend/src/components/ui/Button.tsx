import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/components/ui/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-[13px] font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary-100 focus-visible:border-primary disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        ghost:
          "text-ink-2 disabled:text-line-strong hover:bg-hover hover:text-ink dark:text-gray-300 dark:hover:bg-gray-700 dark:hover:text-white dark:disabled:text-gray-600",
        primary: "border border-primary bg-primary text-white hover:bg-primary-hover hover:border-primary-hover disabled:bg-primary-disabled disabled:border-primary-disabled disabled:opacity-100",
        outline:
          "border border-line-strong text-ink bg-white hover:bg-hover dark:border-gray-600 dark:text-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 dark:hover:border-gray-500",
        stop: "bg-bad text-white hover:bg-red-600 disabled:bg-red-300 dark:bg-red-600 dark:hover:bg-red-700 dark:disabled:bg-red-900",
      },
      size: {
        default: "h-[34px] px-3.5",
        sm: "h-7 px-2.5 text-xs",
        lg: "h-10 px-5 text-sm",
        icon: "h-10 w-10 rounded-md [&_svg]:size-5",
        iconSmall: "h-8 w-8 rounded-md [&_svg]:size-4",
        iconTiny: "h-6 w-6 rounded-md [&_svg]:size-3",
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
