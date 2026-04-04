"use client";

import useSWR from "swr";
import { api } from "@/lib/api-client";
import type { User, UserPreferences } from "@/types/api";
import { useAuthStore } from "@/lib/auth";

export function useProfile() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<User>(isAuthenticated ? "/users/me" : null, api.get);
}

export function usePreferences() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return useSWR<UserPreferences>(
    isAuthenticated ? "/users/me/preferences" : null,
    api.get
  );
}
