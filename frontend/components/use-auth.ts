"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { AuthResponse } from "@/lib/types";

export function useAuth() {
  const router = useRouter();
  const query = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<AuthResponse>("/auth/me"),
    retry: false
  });

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      router.push("/login");
    }
  }, [query.error, router]);

  return query;
}
