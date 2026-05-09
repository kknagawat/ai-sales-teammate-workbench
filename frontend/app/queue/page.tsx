"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Building2, Search, SlidersHorizontal } from "lucide-react";
import { AppShell } from "@/components/shell";
import { useAuth } from "@/components/use-auth";
import { EmptyState, ErrorNotice, Panel, TextInput } from "@/components/ui";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { apiFetch, ApiError } from "@/lib/api";
import { cn, formatDate, humanize, isTransient } from "@/lib/format";
import type { PublicConfig, WorkItemListResponse, WorkItemStatus } from "@/lib/types";

const statuses: Array<"ALL" | WorkItemStatus> = [
  "ALL",
  "PENDING_REVIEW",
  "FAILED",
  "PROCESSING",
  "REGENERATING",
  "SENT",
  "REJECTED"
];

const priorityRank = {
  URGENT: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1
};

type QueueSort = "CURRENT" | "PRIORITY" | "INTENT" | "FIT" | "NEWEST" | "LEAD";

const sortOptions: Array<{ value: QueueSort; label: string }> = [
  { value: "CURRENT", label: "Current" },
  { value: "PRIORITY", label: "Priority" },
  { value: "INTENT", label: "Intent" },
  { value: "FIT", label: "Fit" },
  { value: "NEWEST", label: "Newest" },
  { value: "LEAD", label: "Lead A-Z" }
];

function timeValue(value: string) {
  return new Date(value).getTime();
}

export default function QueuePage() {
  const auth = useAuth();
  const [status, setStatus] = useState<(typeof statuses)[number]>("ALL");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<QueueSort>("CURRENT");

  const config = useQuery({
    queryKey: ["config", "public"],
    queryFn: () => apiFetch<PublicConfig>("/config/public")
  });

  const queue = useQuery({
    queryKey: ["work-items"],
    queryFn: () => apiFetch<WorkItemListResponse>("/work-items"),
    refetchInterval: (query) => {
      if (query.state.error) return false;
      const items = query.state.data?.items ?? [];
      const shouldPoll = items.some((item) => isTransient(item.status));
      return shouldPoll && typeof document !== "undefined" && !document.hidden ? 5000 : false;
    },
    refetchIntervalInBackground: false
  });

  const filteredItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    const items = (queue.data?.items ?? []).filter((item) => {
      const matchesStatus = status === "ALL" || item.status === status;
      const haystack = [
        item.lead_name,
        item.lead_email,
        item.company_name,
        item.lead_title,
        item.lead_source,
        item.source_event_type
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return matchesStatus && (!term || haystack.includes(term));
    });
    return [...items].sort((a, b) => {
      if (sort === "PRIORITY") {
        return priorityRank[b.priority] - priorityRank[a.priority] || timeValue(b.updated_at) - timeValue(a.updated_at);
      }
      if (sort === "INTENT") {
        return b.intent_score - a.intent_score || timeValue(b.updated_at) - timeValue(a.updated_at);
      }
      if (sort === "FIT") {
        return b.fit_score - a.fit_score || timeValue(b.updated_at) - timeValue(a.updated_at);
      }
      if (sort === "NEWEST") {
        return timeValue(b.created_at) - timeValue(a.created_at);
      }
      if (sort === "LEAD") {
        return a.lead_name.localeCompare(b.lead_name);
      }
      return timeValue(b.updated_at) - timeValue(a.updated_at);
    });
  }, [queue.data?.items, search, sort, status]);

  const user = auth.data?.user;
  if (!user) {
    return <main className="min-h-screen bg-paper" />;
  }

  const error =
    queue.error instanceof ApiError ? queue.error.detail : queue.error ? "Queue failed to load." : null;

  return (
    <AppShell user={user} config={config.data}>
      <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <p className="text-sm font-bold uppercase tracking-wide text-moss">Reviewer queue</p>
          <h1 className="mt-2 text-3xl font-bold text-ink">{filteredItems.length} work items</h1>
        </div>
        <div className="grid gap-3 sm:grid-cols-[280px_auto]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
            <TextInput
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9"
              placeholder="Search leads or companies"
            />
          </div>
          <div className="flex overflow-x-auto rounded-full border border-line bg-white p-1 shadow-sm">
            {statuses.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setStatus(option)}
                className={cn(
                  "h-9 whitespace-nowrap rounded-full px-3 text-sm font-semibold text-slate-500 transition",
                  status === option && "bg-ink text-white"
                )}
              >
                {option === "ALL" ? "All" : humanize(option)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? <ErrorNotice message={error} /> : null}

      <Panel
        action={
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-500">
            <SlidersHorizontal className="h-4 w-4" />
            <span>{queue.isFetching ? "Refreshing" : "Sort"}</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value as QueueSort)}
              className="h-9 rounded-full border border-line bg-white px-3 text-sm font-semibold text-ink outline-none focus:border-moss"
            >
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {filteredItems.length === 0 && !queue.isLoading ? (
          <EmptyState title="No matching work items" detail="Adjust the filter or search term." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] border-collapse text-left">
              <thead>
                <tr className="border-b border-line text-xs font-bold uppercase tracking-wide text-[#64748b]">
                  <th className="py-3 pr-4">Lead</th>
                  <th className="px-4 py-3">Signal</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Scores</th>
                  <th className="px-4 py-3">Owner</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="py-3 pl-4">Updated</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item) => (
                  <tr key={item.id} className="border-b border-line/80 last:border-0">
                    <td className="py-4 pr-4">
                      <Link href={`/work-items/${item.id}`} className="group block">
                        <div className="font-bold text-ink group-hover:text-moss">{item.lead_name}</div>
                        <div className="mt-1 flex items-center gap-2 text-sm text-[#64748b]">
                          <Building2 className="h-4 w-4" />
                          <span>{item.lead_title ?? "Lead"}</span>
                          <span>at</span>
                          <span>{item.company_name}</span>
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-4">
                      <div className="text-sm font-semibold text-ink">{item.source_event_type}</div>
                      <div className="mt-1 text-sm text-[#64748b]">{item.lead_source}</div>
                    </td>
                    <td className="px-4 py-4 text-sm font-semibold text-ink">{item.buying_stage}</td>
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        <Activity className="h-4 w-4 text-moss" />
                        <span>{item.intent_score}</span>
                        <span className="text-[#94a3b8]">/</span>
                        <span>{item.fit_score}</span>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-sm text-[#64748b]">
                      {item.assigned_reviewer?.name ?? "Unassigned"}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        <StatusBadge status={item.status} />
                        <PriorityBadge priority={item.priority} />
                      </div>
                    </td>
                    <td className="py-4 pl-4 text-sm text-[#64748b]">{formatDate(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
