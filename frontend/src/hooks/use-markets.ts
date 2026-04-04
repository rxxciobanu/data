"use client";

import useSWR from "swr";
import { api } from "@/lib/api-client";
import type { Market, DebateDetail } from "@/types/api";
import { useAuthStore } from "@/lib/auth";

export function useMarkets(page = 1, limit = 50) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<Market[]>(
    isAuthenticated ? `/markets?page=${page}&limit=${limit}` : null,
    api.get
  );
}

export function useMarketDetail(id: string | null) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<Market>(
    isAuthenticated && id ? `/markets/${id}` : null,
    api.get
  );
}

export function useMarketDebate(id: string | null) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<DebateDetail>(
    isAuthenticated && id ? `/markets/${id}/debate` : null,
    api.get
  );
}
