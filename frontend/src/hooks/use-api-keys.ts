"use client";

import useSWR from "swr";
import { api } from "@/lib/api-client";
import type { ApiKey, ApiKeyCreated } from "@/types/api";
import { useAuthStore } from "@/lib/auth";

export function useApiKeys() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const swr = useSWR<ApiKey[]>(
    isAuthenticated ? "/auth/api-keys" : null,
    api.get
  );

  const createKey = async (label: string): Promise<ApiKeyCreated> => {
    const result = await api.post<ApiKeyCreated>("/auth/api-keys", { label });
    swr.mutate();
    return result;
  };

  const deleteKey = async (id: string): Promise<void> => {
    await api.delete(`/auth/api-keys/${id}`);
    swr.mutate();
  };

  return { ...swr, createKey, deleteKey };
}
