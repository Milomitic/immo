"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createAlert, deleteAlert, fetchAlerts, markAlertSeen, updateAlert } from "@/lib/api";

const ALERTS_KEY = ["alerts"] as const;

/** Saved searches with their counts. Shared by the header badge and /alerts. */
export function useAlerts() {
  return useQuery({ queryKey: ALERTS_KEY, queryFn: fetchAlerts, staleTime: 60_000 });
}

function useAlertMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => qc.invalidateQueries({ queryKey: ALERTS_KEY }),
  });
}

export function useCreateAlert() {
  return useAlertMutation(({ name, filters }: { name: string; filters: Record<string, string> }) =>
    createAlert(name, filters),
  );
}

export function useUpdateAlert() {
  return useAlertMutation(({ id, ...patch }: { id: string; name?: string; is_active?: boolean }) =>
    updateAlert(id, patch),
  );
}

export function useMarkAlertSeen() {
  return useAlertMutation((id: string) => markAlertSeen(id));
}

export function useDeleteAlert() {
  return useAlertMutation((id: string) => deleteAlert(id));
}
