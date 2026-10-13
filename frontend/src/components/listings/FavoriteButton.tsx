"use client";

import { Heart } from "lucide-react";
import { useFavoriteIds, useToggleFavorite } from "@/hooks/useFavorites";
import { cn } from "@/lib/utils";

interface FavoriteButtonProps {
  listingId: string;
  size?: "sm" | "md";
  className?: string;
}

export function FavoriteButton({ listingId, size = "sm", className }: FavoriteButtonProps) {
  const { ids } = useFavoriteIds();
  const toggle = useToggleFavorite();
  const saved = ids.has(listingId);
  const label = saved ? "Rimuovi dai preferiti" : "Salva nei preferiti";

  return (
    <button
      type="button"
      onClick={(e) => {
        // Cards can sit inside clickable areas: don't let the click through.
        e.preventDefault();
        e.stopPropagation();
        toggle.mutate({ id: listingId, save: !saved });
      }}
      aria-pressed={saved}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center justify-center rounded-full bg-white/90 shadow-sm transition-transform hover:bg-white active:scale-90",
        size === "sm" ? "h-8 w-8" : "h-10 w-10",
        className,
      )}
    >
      <Heart
        className={cn(
          size === "sm" ? "h-4 w-4" : "h-5 w-5",
          saved ? "fill-red-500 text-red-500" : "text-gray-700",
        )}
      />
    </button>
  );
}
