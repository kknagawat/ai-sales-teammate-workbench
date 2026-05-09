"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, ClipboardList, CloudCog, Loader2, UsersRound } from "lucide-react";
import { AppShell } from "@/components/shell";
import { useAuth } from "@/components/use-auth";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { Badge, Button, EmptyState, ErrorNotice, Panel } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate, humanize } from "@/lib/format";
import type {
  AdminUsersResponse,
  AuditLogListResponse,
  LLMProvider,
  PublicConfig,
  WorkItemListResponse
} from "@/lib/types";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.detail : error ? fallback : null;
}

export default function AdminPage() {
  const queryClient = useQueryClient();
  const auth = useAuth();
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const config = useQuery({
    queryKey: ["config", "public"],
    queryFn: () => apiFetch<PublicConfig>("/config/public")
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => apiFetch<AdminUsersResponse>("/admin/users"),
    enabled: auth.data?.user.role === "ADMIN"
  });
  const workItems = useQuery({
    queryKey: ["admin", "work-items"],
    queryFn: () => apiFetch<WorkItemListResponse>("/admin/work-items"),
    enabled: auth.data?.user.role === "ADMIN"
  });
  const auditLogs = useQuery({
    queryKey: ["admin", "audit-logs"],
    queryFn: () => apiFetch<AuditLogListResponse>("/admin/audit-logs"),
    enabled: auth.data?.user.role === "ADMIN"
  });

  const switchProvider = useMutation({
    mutationFn: (provider: LLMProvider) =>
      apiFetch<PublicConfig>("/config/runtime/llm-provider", {
        method: "PATCH",
        json: { provider }
      }),
    onSuccess: async () => {
      setRuntimeError(null);
      await queryClient.invalidateQueries({ queryKey: ["config", "public"] });
    },
    onError: (error) =>
      setRuntimeError(error instanceof ApiError ? error.detail : "Provider switch failed.")
  });

  function requestProviderSwitch(provider: LLMProvider) {
    const label = provider === "anthropic" ? "Claude" : "Mock";
    if (!window.confirm(`Switch this organization's AI provider to ${label}?`)) return;
    switchProvider.mutate(provider);
  }

  const user = auth.data?.user;
  if (!user) return <main className="min-h-screen bg-paper" />;

  const error =
    errorMessage(users.error, "Users failed to load.") ??
    errorMessage(workItems.error, "Work items failed to load.") ??
    errorMessage(auditLogs.error, "Audit logs failed to load.");

  return (
    <AppShell user={user} config={config.data}>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <Link href="/queue" className="inline-flex items-center gap-2 text-sm font-semibold text-moss">
            <ArrowLeft className="h-4 w-4" />
            Queue
          </Link>
          <h1 className="mt-3 text-3xl font-bold text-ink">Admin Console</h1>
        </div>
      </div>

      {user.role !== "ADMIN" ? <ErrorNotice message="Admin access required." /> : null}
      {error ? <div className="mb-4"><ErrorNotice message={error} /></div> : null}

      {user.role === "ADMIN" ? (
        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <Panel title="Runtime AI Provider" className="xl:col-span-2">
            <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="border-[#0047AF]/30 bg-sage text-moss">
                    {config.data?.llm.provider === "anthropic" ? (
                      <CloudCog className="h-3.5 w-3.5" />
                    ) : (
                      <Bot className="h-3.5 w-3.5" />
                    )}
                    <span className="ml-1.5">
                      {config.data?.llm.provider === "anthropic" ? "Claude mode" : "Mock mode"}
                    </span>
                  </Badge>
                  <Badge className="border-line bg-white text-[#64748b]">
                    {config.data?.llm.model_label ?? "Loading"}
                  </Badge>
                  <Badge className="border-line bg-white text-[#64748b]">
                    {config.data?.llm.active_provider_source === "runtime_override"
                      ? "Runtime override"
                      : "Environment"}
                  </Badge>
                </div>
                <div className="mt-3 grid gap-2 text-sm text-[#64748b] sm:grid-cols-3">
                  <span>Structured outputs: {config.data?.llm.structured_outputs_enabled ? "on" : "off"}</span>
                  <span>Decision trace: {config.data?.llm.decision_trace_enabled ? "on" : "off"}</span>
                  <span>Claude configured: {config.data?.llm.anthropic_configured ? "yes" : "no"}</span>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 lg:justify-end">
                <Button
                  onClick={() => requestProviderSwitch("mock")}
                  disabled={
                    switchProvider.isPending ||
                    !config.data?.llm.runtime_switching_enabled ||
                    !config.data?.llm.available_providers.includes("mock") ||
                    config.data?.llm.provider === "mock"
                  }
                >
                  {switchProvider.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
                  Use Mock
                </Button>
                <Button
                  onClick={() => requestProviderSwitch("anthropic")}
                  disabled={
                    switchProvider.isPending ||
                    !config.data?.llm.runtime_switching_enabled ||
                    !config.data?.llm.available_providers.includes("anthropic") ||
                    config.data?.llm.provider === "anthropic"
                  }
                  variant="primary"
                >
                  {switchProvider.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <CloudCog className="h-4 w-4" />
                  )}
                  Use Claude
                </Button>
              </div>
            </div>
            {!config.data?.llm.runtime_switching_enabled ? (
              <p className="mt-4 text-sm font-medium text-[#64748b]">
                Runtime switching is disabled. Set `LLM_RUNTIME_SWITCHING_ENABLED=true` on the
                backend to enable demo switching.
              </p>
            ) : null}
            {runtimeError ? <div className="mt-4"><ErrorNotice message={runtimeError} /></div> : null}
          </Panel>

          <Panel title="Users">
            {(users.data?.items ?? []).length ? (
              <div className="space-y-3">
                {users.data?.items.map((adminUser) => (
                  <div
                    key={adminUser.id}
                    className="flex items-center justify-between gap-3 rounded-md border border-line bg-[#f8fafc] p-3"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 font-bold text-ink">
                        <UsersRound className="h-4 w-4 text-moss" />
                        <span className="truncate">{adminUser.name}</span>
                      </div>
                      <div className="mt-1 truncate text-sm text-[#64748b]">{adminUser.email}</div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Badge className="border-line bg-white text-[#64748b]">{adminUser.role}</Badge>
                      <Badge
                        className={
                          adminUser.is_active
                            ? "border-[#10b981]/30 bg-[#ecfdf5] text-[#047857]"
                            : "border-coral/30 bg-[#fff1f2] text-[#be123c]"
                        }
                      >
                        {adminUser.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No users" />
            )}
          </Panel>

          <Panel title="Organization Work Items">
            {(workItems.data?.items ?? []).length ? (
              <div className="space-y-3">
                {workItems.data?.items.map((item) => (
                  <Link
                    href={`/work-items/${item.id}`}
                    key={item.id}
                    className="block rounded-md border border-line bg-[#f8fafc] p-3 hover:bg-sage"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-bold text-ink">{item.lead_name}</div>
                        <div className="mt-1 text-sm text-[#64748b]">
                          {item.company_name} · {item.source_event_type}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap justify-end gap-2">
                        <StatusBadge status={item.status} />
                        <PriorityBadge priority={item.priority} />
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <EmptyState title="No work items" />
            )}
          </Panel>

          <Panel title="Audit Log" className="xl:col-span-2">
            {(auditLogs.data?.items ?? []).length ? (
              <div className="grid gap-3 lg:grid-cols-2">
                {auditLogs.data?.items.slice(0, 30).map((entry) => (
                  <div key={entry.id} className="rounded-md border border-line bg-[#f8fafc] p-3">
                    <div className="flex items-center gap-2 text-sm font-bold text-ink">
                      <ClipboardList className="h-4 w-4 text-moss" />
                      {humanize(entry.action)}
                    </div>
                    <div className="mt-1 text-xs text-[#64748b]">
                      {entry.actor_name ?? "System"} · {formatDate(entry.created_at)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="No audit entries" />
            )}
          </Panel>
        </div>
      ) : null}
    </AppShell>
  );
}
