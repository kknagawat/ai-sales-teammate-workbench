"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bot, LogOut, UserRound } from "lucide-react";
import { apiFetch } from "@/lib/api";
import type { PublicConfig, User } from "@/lib/types";
import { ProviderBadge } from "./badges";
import { IconButton } from "./ui";

export function AppShell({
  user,
  config,
  children
}: {
  user: User;
  config?: PublicConfig;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const showProviderBadge = user.role === "ADMIN" && pathname.startsWith("/admin");

  async function logout() {
    await apiFetch<void>("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.push("/login");
  }

  return (
    <main className="mx-auto min-h-screen max-w-7xl border-x border-line bg-white">
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur">
        <div className="bg-black px-4 py-2 text-center text-xs font-semibold text-white">
          AI Sales Teammate Workbench · Human review, async approval, and audit trails
        </div>
        <div className="px-4 py-3 sm:px-6 lg:px-8">
          <div className="mx-auto flex h-[60px] items-center justify-between gap-4 rounded-full border border-line bg-white px-3 shadow-sm">
            <div className="flex min-w-0 items-center gap-4">
              <Link href="/queue" className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-moss text-white">
                  <Bot className="h-5 w-5" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-extrabold tracking-tight text-ink">
                    Teammates.ai
                  </span>
                  <span className="block truncate text-xs font-semibold text-slate-500">Sales review workbench</span>
                </span>
              </Link>
              {user.role === "ADMIN" ? (
                <Link
                  href="/admin"
                  className="hidden rounded-full px-4 py-2 text-sm font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-ink sm:inline-flex"
                >
                  Admin
                </Link>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              {showProviderBadge ? <ProviderBadge config={config} /> : null}
              <div className="hidden items-center gap-2 rounded-full border border-line bg-white px-3 py-2 text-sm shadow-sm sm:flex">
                <UserRound className="h-4 w-4 text-moss" />
                <span className="max-w-[180px] truncate font-semibold">{user.name}</span>
              </div>
              <IconButton label="Log out" onClick={logout}>
                <LogOut className="h-4 w-4" />
              </IconButton>
            </div>
          </div>
        </div>
      </header>
      <div className="px-4 py-6 sm:px-6 lg:px-8">{children}</div>
    </main>
  );
}
