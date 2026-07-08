"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { formatPrice, timeAgo } from "@/lib/utils";

interface PriceChangeBadgeProps {
  price: number | null;
  pricePrevious: number | null;
  priceChangedAt: string | null;
  size?: "sm" | "md";
  /** Show the previous price strikethrough beside the badge. */
  showPrevious?: boolean;
}

/**
 * Visual marker for listings whose listed price changed since we first
 * scraped them. Green ↓ for reductions (more common, what most users
 * are looking for), red ↑ for increases. Hidden when there's no change
 * recorded.
 */
export function PriceChangeBadge({
  price,
  pricePrevious,
  priceChangedAt,
  size = "sm",
  showPrevious = false,
}: PriceChangeBadgeProps) {
  if (price == null || pricePrevious == null || pricePrevious === price) {
    return null;
  }

  const delta = price - pricePrevious;
  const pct = (delta / pricePrevious) * 100;
  const isReduction = delta < 0;

  const Icon = isReduction ? TrendingDown : TrendingUp;
  const colorClass = isReduction
    ? "bg-green-100 text-green-800 border-green-300"
    : "bg-red-100 text-red-700 border-red-300";
  const sizeClass =
    size === "md"
      ? "text-sm px-2.5 py-1 gap-1.5"
      : "text-[11px] px-2 py-0.5 gap-1";
  const iconSize = size === "md" ? "h-3.5 w-3.5" : "h-3 w-3";

  return (
    <span className="inline-flex items-center gap-2">
      {showPrevious && (
        <span className="text-[var(--muted-foreground)] line-through text-xs">
          {formatPrice(pricePrevious)}
        </span>
      )}
      <span
        className={`inline-flex items-center rounded-full border font-semibold ${colorClass} ${sizeClass}`}
        title={
          priceChangedAt
            ? `Variato ${timeAgo(priceChangedAt)} • prima ${formatPrice(pricePrevious)}`
            : `Prima ${formatPrice(pricePrevious)}`
        }
      >
        <Icon className={iconSize} />
        {isReduction ? "" : "+"}
        {pct.toFixed(0)}%
      </span>
    </span>
  );
}
