"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "destructive" | "outline";
type BadgeSize = "sm" | "md";

interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  removable?: boolean;
  onRemove?: () => void;
  className?: string;
  children: React.ReactNode;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-[var(--muted)] text-[var(--foreground)]",
  primary: "bg-[var(--primary)] text-[var(--primary-foreground)]",
  success: "bg-emerald-100 text-emerald-800",
  warning: "bg-amber-100 text-amber-800",
  destructive: "bg-red-100 text-red-800",
  outline: "border border-[var(--border)] text-[var(--foreground)] bg-[var(--background)]",
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "text-[10px] px-1.5 py-0.5 gap-1",
  md: "text-xs px-2.5 py-1 gap-1.5",
};

export function Badge({ variant = "default", size = "md", removable, onRemove, className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-medium whitespace-nowrap transition-colors",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
    >
      {children}
      {removable && (
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); onRemove?.(); }}
          className="inline-flex items-center justify-center rounded-full hover:bg-black/10 transition-colors -mr-0.5"
        >
          <X className={size === "sm" ? "h-2.5 w-2.5" : "h-3 w-3"} />
        </button>
      )}
    </span>
  );
}
