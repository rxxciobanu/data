"use client";

import useSWR from "swr";
import { api } from "@/lib/api-client";
import type { WhaleConfig, WhaleLeaderboardEntry } from "@/types/api";
import { useAuthStore } from "@/lib/auth";

export function useWhaleConfig() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<WhaleConfig>(
    isAuthenticated ? "/whales/config" : null,
    api.get
  );
}

export function useWhaleSignals(page = 1, limit = 20) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR(
    isAuthenticated ? `/whales/signals?page=${page}&limit=${limit}` : null,
    api.get
  );
}

export function useWhaleLeaderboard() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<WhaleLeaderboardEntry[]>(
    isAuthenticated ? "/whales/leaderboard" : null,
    api.get
  );
}
