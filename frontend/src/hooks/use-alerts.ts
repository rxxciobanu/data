"use client";

import useSWR from "swr";
import { api } from "@/lib/api-client";
import type { Alert, AlertStats } from "@/types/api";
import { useAuthStore } from "@/lib/auth";

export function useAlerts(page = 1, limit = 20) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<Alert[]>(
    isAuthenticated ? `/alerts?page=${page}&limit=${limit}` : null,
    api.get
  );
}

export function useLatestAlerts() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<Alert[]>(
    isAuthenticated ? "/alerts/latest" : null,
    api.get
  );
}

export function useAlertDetail(id: string | null) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<Alert>(
    isAuthenticated && id ? `/alerts/${id}` : null,
    api.get
  );
}

export function useAlertStats() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<AlertStats>(
    isAuthenticated ? "/alerts/stats" : null,
    api.get
  );
}
