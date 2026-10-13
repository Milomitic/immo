"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchFavoriteIds, fetchFavorites, removeFavorite, saveFavorite } from "@/lib/api";

const IDS_KEY = ["favorite-ids"] as const;
const LIST_KEY = ["favorites"] as const;

/** Saved listing ids. Every heart on the page shares this one query. */
export function useFavoriteIds() {
  const query = useQuery({ queryKey: IDS_KEY, queryFn: fetchFavoriteIds, staleTime: 60_000 });
  const ids = useMemo(() => new Set(query.data ?? []), [query.data]);
  return { ...query, ids };
}

export function useFavorites() {
  return useQuery({ queryKey: LIST_KEY, queryFn: fetchFavorites });
}

/** Optimistic toggle: the heart flips at once and rolls back if the API
 *  refuses (network error, or 401 when ADMIN_TOKEN is set). */
export function useToggleFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, save }: { id: string; save: boolean }): Promise<void> => {
      if (save) await saveFavorite(id);
      else await removeFavorite(id);
    },
    onMutate: async ({ id, save }) => {
      await qc.cancelQueries({ queryKey: IDS_KEY });
      const previous = qc.getQueryData<string[]>(IDS_KEY);
      qc.setQueryData<string[]>(IDS_KEY, (old = []) =>
        save ? [...new Set([...old, id])] : old.filter((x) => x !== id),
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(IDS_KEY, context.previous);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: IDS_KEY });
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
  });
}
