"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface FilterSectionProps {
  title: string;
  defaultOpen?: boolean;
  count?: number;
  /** false: a plain titled block, always open (the map's filter bar lays
   *  sections side by side, where an accordion makes no sense). */
  collapsible?: boolean;
  children: React.ReactNode;
}

export function FilterSection({ title, defaultOpen = true, count, collapsible = true, children }: FilterSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  const heading = (
    <span className="text-sm font-semibold flex items-center gap-2">
      {title}
      {count !== undefined && count > 0 && (
        <span className="inline-flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-[10px] font-bold">
          {count}
        </span>
      )}
    </span>
  );

  if (!collapsible) {
    return (
      <div className="min-w-0">
        <div className="pb-2">{heading}</div>
        {children}
      </div>
    );
  }

  return (
    <div className="border-b border-[var(--border)] last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-3 text-left"
      >
        {heading}
        <ChevronDown
          className={cn(
            "h-4 w-4 text-[var(--muted-foreground)] transition-transform duration-200",
            open && "rotate-180"
          )}
        />
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  );
}
