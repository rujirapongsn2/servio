import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/components/ui/utils";

/*
 * Themed on the design tokens (see app/globals.css). No raw hex values:
 * light/dark both resolve through the token layer. Motion follows the
 * reference: colour/opacity transitions only — no scale bounce.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium press cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        ghost:
          "text-charcoal hover:bg-hover hover:text-fg disabled:text-stone dark:text-fg-2 dark:hover:bg-hover dark:hover:text-fg dark:disabled:text-stone",
        primary: "bg-brand text-primary-foreground hover:bg-brand-strong disabled:opacity-50 disabled:cursor-not-allowed",
        outline:
          "border border-hairline text-fg bg-surface hover:bg-hover hover:border-stone dark:border-hairline dark:text-fg dark:bg-surface dark:hover:bg-hover dark:hover:border-stone",
        stop: "bg-danger text-white hover:bg-danger/90 disabled:opacity-50",
      },
      size: {
        xs: "h-6 px-2 text-xs",
        default: "h-[30px] px-3.5 text-sm",
        sm: "h-7 px-3 text-xs",
        lg: "h-10 px-6 text-base",
        icon: "h-9 w-9 rounded-full [&_svg]:size-5",
        iconSmall: "h-7 w-7 rounded-full [&_svg]:size-4",
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
