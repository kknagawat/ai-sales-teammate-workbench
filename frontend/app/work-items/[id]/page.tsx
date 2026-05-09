"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Building2,
  CheckCircle2,
  Clock3,
  FileText,
  Loader2,
  Mail,
  Phone,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  Sparkles,
  UserRound,
  XCircle
} from "lucide-react";
import { AppShell } from "@/components/shell";
import { useAuth } from "@/components/use-auth";
import { PriorityBadge, StatusBadge } from "@/components/badges";
import { Badge, Button, EmptyState, ErrorNotice, FieldLabel, Panel, TextArea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { canReview, cn, formatDate, getString, getStringArray, humanize, isTransient } from "@/lib/format";
import type {
  AuditLogListResponse,
  DecisionTrace,
  GenerationRunListResponse,
  PreviousTouchpoint,
  PublicConfig,
  QualityChecks,
  WorkItemDetail
} from "@/lib/types";

function detailFromError(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.detail : error ? fallback : null;
}

function readObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function qualityChecks(item?: WorkItemDetail): QualityChecks {
  const output = readObject(item?.latest_generation_run?.structured_output);
  return readObject(output.quality_checks) as QualityChecks;
}

function traceFor(item?: WorkItemDetail): DecisionTrace {
  const output = readObject(item?.latest_generation_run?.structured_output);
  return (item?.latest_generation_run?.decision_trace ??
    readObject(output.decision_trace)) as DecisionTrace;
}

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function display(value: unknown, fallback = "Not available") {
  if (typeof value === "number") return String(value);
  return hasText(value) ? value : fallback;
}

function FieldRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="grid gap-1 border-b border-line/70 py-2 last:border-0 sm:grid-cols-[132px_1fr]">
      <dt className="text-xs font-bold uppercase tracking-wide text-[#64748b]">{label}</dt>
      <dd className="text-sm font-medium leading-5 text-ink">{display(value)}</dd>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-bold text-ink">{label}</span>
        <span className="font-semibold text-moss">{clamped}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[#e2e8f0]">
        <div className="h-full rounded-full bg-moss" style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

function ChipList({ values }: { values: string[] }) {
  if (!values.length) return <p className="text-sm text-[#64748b]">None recorded.</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value) => (
        <Badge key={value} className="border-line bg-[#f8fafc] text-[#334155]">
          {value}
        </Badge>
      ))}
    </div>
  );
}

function TextBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">{label}</div>
      <p className="text-sm leading-6 text-ink">{display(value)}</p>
    </div>
  );
}

function BooleanCheck({ label, value }: { label: string; value?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/70 py-2 text-sm last:border-0">
      <span className="font-medium text-[#334155]">{label}</span>
      {value ? (
        <CheckCircle2 className="h-4 w-4 text-moss" />
      ) : (
        <XCircle className="h-4 w-4 text-[#94a3b8]" />
      )}
    </div>
  );
}

function ContextSection({
  title,
  icon,
  children,
  defaultOpen = true
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen} className="group border-b border-line/80 py-4 last:border-0">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-[#475569]">
          {icon}
          {title}
        </span>
        <span className="text-xs font-semibold text-[#64748b] group-open:hidden">Open</span>
        <span className="text-xs font-semibold text-[#64748b] hidden group-open:inline">Close</span>
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}

function GenerationOverlay() {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/78 backdrop-blur-sm">
      <div className="rounded-lg border border-[#0047AF]/40 bg-[#eaf2ff] px-5 py-4 text-center shadow-panel">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-white text-moss">
          <Sparkles className="h-5 w-5 animate-pulse" />
        </div>
        <div className="mt-3 text-sm font-bold text-ink">Generating draft</div>
        <div className="mt-2 flex justify-center gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-moss [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-moss [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-moss" />
        </div>
      </div>
    </div>
  );
}

function Touchpoints({ values }: { values?: PreviousTouchpoint[] }) {
  if (!values?.length) return <p className="text-sm text-[#64748b]">None recorded.</p>;
  return (
    <div className="space-y-3">
      {values.map((touchpoint, index) => (
        <div key={`${touchpoint.channel ?? "touchpoint"}-${index}`} className="border-l-2 border-sage pl-3">
          <div className="text-sm font-bold text-ink">{display(touchpoint.channel, "Touchpoint")}</div>
          <div className="mt-1 text-sm leading-5 text-[#64748b]">{display(touchpoint.summary)}</div>
          {touchpoint.occurred_at ? (
            <div className="mt-1 text-xs text-[#64748b]">{formatDate(touchpoint.occurred_at)}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function SaveState({
  canAct,
  draftChanged,
  isGenerating,
  isSaving
}: {
  canAct: boolean;
  draftChanged: boolean;
  isGenerating: boolean;
  isSaving: boolean;
}) {
  let label = "Saved";
  let tone = "text-moss";
  if (isSaving) {
    label = "Saving";
    tone = "text-[#64748b]";
  } else if (isGenerating) {
    label = "Locked while generating";
    tone = "text-[#64748b]";
  } else if (!canAct) {
    label = "Editing locked";
    tone = "text-[#64748b]";
  } else if (draftChanged) {
    label = "Unsaved changes";
    tone = "text-amber";
  }

  return (
    <div className={cn("mt-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wide", tone)}>
      {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
      {label}
    </div>
  );
}

function ProcessingStatusPanel({
  item,
  onRetry,
  retrying
}: {
  item: WorkItemDetail;
  onRetry: () => void;
  retrying: boolean;
}) {
  const latestJob = item.background_jobs[0] ?? null;
  const showRetry = item.status === "FAILED" || item.status === "PROCESSING";
  const isActive = latestJob?.status === "QUEUED" || latestJob?.status === "RUNNING";
  const title =
    item.status === "SENT"
      ? "Processing complete"
      : item.status === "FAILED"
        ? "Processing failed"
        : item.status === "PROCESSING"
          ? "Processing in progress"
          : "Processing status";
  const description =
    item.status === "PROCESSING"
      ? isActive
        ? "The backend worker is handling the approved follow-up. This page polls until it becomes sent or failed."
        : "This item is processing but no active worker job is visible. Retry can create a recovery job."
      : item.status === "FAILED"
        ? "The backend workflow needs attention. Retry processing will use the approved draft snapshot."
        : item.status === "SENT"
          ? "The approved follow-up was sent through the simulated backend workflow."
          : latestJob
            ? "Most recent approval processing job is shown below."
            : "Approval has not created a processing job yet.";

  return (
    <Panel title={title}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-sm leading-6 text-[#64748b]">{description}</p>
          {latestJob ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge className="border-line bg-white text-[#64748b]">{humanize(latestJob.status)}</Badge>
              <Badge className="border-line bg-white text-[#64748b]">
                Attempt {latestJob.attempt_count}/{latestJob.max_attempts}
              </Badge>
              <Badge className="border-line bg-white text-[#64748b]">
                {formatDate(latestJob.started_at ?? latestJob.created_at)}
              </Badge>
            </div>
          ) : null}
          {latestJob?.error_message ? (
            <div className="mt-3 text-sm font-semibold text-[#be123c]">{latestJob.error_message}</div>
          ) : null}
        </div>
        {showRetry ? (
          <Button onClick={onRetry} disabled={retrying}>
            {retrying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            {item.status === "PROCESSING" ? "Retry if stuck" : "Retry processing"}
          </Button>
        ) : null}
      </div>
    </Panel>
  );
}

export default function WorkItemDetailPage() {
  const params = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const auth = useAuth();
  const [draft, setDraft] = useState("");
  const [reviewerFeedback, setReviewerFeedback] = useState("");
  const [reviewerNote, setReviewerNote] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const config = useQuery({
    queryKey: ["config", "public"],
    queryFn: () => apiFetch<PublicConfig>("/config/public")
  });

  const item = useQuery({
    queryKey: ["work-item", params.id],
    queryFn: () => apiFetch<WorkItemDetail>(`/work-items/${params.id}`),
    enabled: Boolean(params.id),
    refetchInterval: (query) => {
      if (query.state.error) return false;
      const status = query.state.data?.status;
      return status && isTransient(status) && typeof document !== "undefined" && !document.hidden
        ? 2000
        : false;
    },
    refetchIntervalInBackground: false
  });

  const audit = useQuery({
    queryKey: ["work-item", params.id, "audit"],
    queryFn: () => apiFetch<AuditLogListResponse>(`/work-items/${params.id}/audit`),
    enabled: Boolean(params.id)
  });

  const runs = useQuery({
    queryKey: ["work-item", params.id, "llm-runs"],
    queryFn: () => apiFetch<GenerationRunListResponse>(`/work-items/${params.id}/llm-runs`),
    enabled: Boolean(params.id)
  });

  useEffect(() => {
    if (item.data) {
      setDraft(item.data.final_draft);
      setReviewerNote(item.data.reviewer_note ?? "");
    }
  }, [item.data]);

  async function refreshAll() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["work-items"] }),
      queryClient.invalidateQueries({ queryKey: ["work-item", params.id] }),
      queryClient.invalidateQueries({ queryKey: ["work-item", params.id, "audit"] }),
      queryClient.invalidateQueries({ queryKey: ["work-item", params.id, "llm-runs"] }),
      queryClient.invalidateQueries({ queryKey: ["config", "public"] })
    ]);
  }

  const approvalIdempotencyKey = useMemo(
    () => `${params.id}:${item.data?.version ?? "loading"}:${crypto.randomUUID()}`,
    [params.id, item.data?.version]
  );

  const saveDraft = useMutation({
    mutationFn: () =>
      apiFetch<WorkItemDetail>(`/work-items/${params.id}/draft`, {
        method: "PATCH",
        json: {
          final_draft: draft,
          last_seen_version: item.data?.version
        }
      }),
    onSuccess: refreshAll,
    onError: (error) => setActionError(detailFromError(error, "Draft save failed."))
  });

  const regenerate = useMutation({
    mutationFn: () =>
      apiFetch<WorkItemDetail>(`/work-items/${params.id}/regenerate`, {
        method: "POST",
        json: {
          reviewer_feedback: reviewerFeedback || null,
          last_seen_version: item.data?.version
        }
      }),
    onSuccess: async () => {
      setReviewerFeedback("");
      await refreshAll();
    },
    onError: (error) => setActionError(detailFromError(error, "Regeneration failed."))
  });

  const approve = useMutation({
    mutationFn: () =>
      apiFetch<WorkItemDetail>(`/work-items/${params.id}/approve`, {
        method: "POST",
        idempotencyKey: approvalIdempotencyKey,
        json: {
          reviewer_note: reviewerNote || null,
          last_seen_version: item.data?.version
        }
      }),
    onSuccess: refreshAll,
    onError: (error) => setActionError(detailFromError(error, "Approval failed."))
  });

  const reject = useMutation({
    mutationFn: () =>
      apiFetch<WorkItemDetail>(`/work-items/${params.id}/reject`, {
        method: "POST",
        json: {
          reviewer_note: reviewerNote || null,
          last_seen_version: item.data?.version
        }
      }),
    onSuccess: refreshAll,
    onError: (error) => setActionError(detailFromError(error, "Rejection failed."))
  });

  const retryProcessing = useMutation({
    mutationFn: () =>
      apiFetch<WorkItemDetail>(`/work-items/${params.id}/retry-processing`, {
        method: "POST",
        json: {
          reviewer_note: reviewerNote || null,
          last_seen_version: item.data?.version
        }
      }),
    onSuccess: refreshAll,
    onError: (error) => setActionError(detailFromError(error, "Retry failed."))
  });

  const current = item.data;
  const user = auth.data?.user;
  const canAct = current ? canReview(current.status) : false;
  const draftChanged = current ? draft !== current.final_draft : false;
  const trace = useMemo(() => traceFor(current), [current]);
  const checks = useMemo(() => qualityChecks(current), [current]);
  const profile = current?.lead_profile ?? {};
  const contact = profile.contact ?? {};
  const company = profile.company ?? {};
  const signal = profile.source_signal ?? {};
  const qualification = profile.qualification ?? {};
  const conversation = profile.conversation_context ?? {};
  const personalization = profile.personalization ?? {};
  const crm = profile.crm ?? {};
  const isGenerating = regenerate.isPending || current?.status === "REGENERATING";

  if (!user) {
    return <main className="min-h-screen bg-paper" />;
  }

  const loadError = detailFromError(item.error, "Work item failed to load.");

  return (
    <AppShell user={user} config={config.data}>
      <div className="mb-5 flex items-center justify-between gap-4">
        <Link href="/queue" className="inline-flex items-center gap-2 text-sm font-semibold text-moss">
          <ArrowLeft className="h-4 w-4" />
          Queue
        </Link>
        {current ? (
          <div className="flex flex-wrap justify-end gap-2">
            <StatusBadge status={current.status} />
            <PriorityBadge priority={current.priority} />
            <Badge className="border-line bg-white text-[#64748b]">v{current.version}</Badge>
          </div>
        ) : null}
      </div>

      {loadError ? <ErrorNotice message={loadError} /> : null}
      {actionError ? <div className="mb-4"><ErrorNotice message={actionError} /></div> : null}

      {!current && item.isLoading ? (
        <Panel>
          <div className="flex items-center gap-3 text-sm font-semibold text-[#64748b]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading work item
          </div>
        </Panel>
      ) : null}

      {current ? (
        <div className="space-y-5">
          <Panel>
            <div className="grid gap-5 lg:grid-cols-[1fr_auto] lg:items-start">
              <div>
                <p className="text-sm font-bold uppercase tracking-wide text-moss">
                  {current.source_event_type}
                </p>
                <h1 className="mt-2 text-3xl font-bold leading-tight text-ink">
                  {current.lead_name}
                </h1>
                <p className="mt-2 text-base leading-7 text-[#64748b]">
                  {current.lead_title ?? contact.title ?? "Lead"} at {current.company_name}
                </p>
              </div>
              <div className="grid min-w-[260px] gap-4 sm:grid-cols-2 lg:grid-cols-1">
                <ScoreBar label="Intent" value={current.intent_score} />
                <ScoreBar label="Fit" value={current.fit_score} />
              </div>
            </div>
          </Panel>

          {isGenerating ? (
            <div className="rounded-lg border border-[#0047AF]/40 bg-[#eaf2ff] px-4 py-3 text-sm font-semibold text-moss">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 animate-pulse" />
                AI is regenerating the draft and decision trace.
              </div>
            </div>
          ) : null}

          {(current.background_jobs.length || current.status === "PROCESSING" || current.status === "FAILED") ? (
            <ProcessingStatusPanel
              item={current}
              onRetry={() => retryProcessing.mutate()}
              retrying={retryProcessing.isPending}
            />
          ) : null}

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(380px,0.85fr)]">
            <div className="space-y-5">
              <Panel
                title="Draft Editor"
                action={
                  <Button
                    onClick={() => saveDraft.mutate()}
                    disabled={!canAct || !draftChanged || saveDraft.isPending || isGenerating}
                    variant="primary"
                  >
                    {saveDraft.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {draftChanged ? "Save changes" : "Saved"}
                  </Button>
                }
              >
                <div className="relative min-h-[380px] overflow-hidden rounded-md">
                  <TextArea
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    disabled={!canAct || isGenerating}
                    className="min-h-[380px] font-mono text-[13px]"
                  />
                  {isGenerating ? <GenerationOverlay /> : null}
                </div>
                <SaveState
                  canAct={canAct}
                  draftChanged={draftChanged}
                  isGenerating={isGenerating}
                  isSaving={saveDraft.isPending}
                />
              </Panel>

              <Panel title="Review Actions">
                <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
                  <div>
                    <FieldLabel>Regeneration feedback</FieldLabel>
                    <TextArea
                      value={reviewerFeedback}
                      onChange={(event) => setReviewerFeedback(event.target.value)}
                      disabled={!canAct || isGenerating}
                      rows={5}
                      placeholder="Ask for a warmer opening, tighter CTA, more technical proof, or a different objection angle."
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        onClick={() => regenerate.mutate()}
                        disabled={!canAct || regenerate.isPending || isGenerating}
                      >
                        {regenerate.isPending || current.status === "REGENERATING" ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Sparkles className="h-4 w-4" />
                        )}
                        Regenerate
                      </Button>
                    </div>
                  </div>
                  <div>
                    <FieldLabel>Reviewer note</FieldLabel>
                    <TextArea
                      value={reviewerNote}
                      onChange={(event) => setReviewerNote(event.target.value)}
                      disabled={!canAct}
                      rows={5}
                      placeholder="Optional note"
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button
                        onClick={() => approve.mutate()}
                        disabled={!canAct || approve.isPending || isGenerating}
                        variant="primary"
                      >
                        {approve.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                        Approve
                      </Button>
                      <Button
                        onClick={() => reject.mutate()}
                        disabled={!canAct || reject.isPending || isGenerating}
                        variant="danger"
                      >
                        {reject.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                        Reject
                      </Button>
                      {current.status === "FAILED" || current.status === "PROCESSING" ? (
                        <Button onClick={() => retryProcessing.mutate()} disabled={retryProcessing.isPending}>
                          {retryProcessing.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <RotateCcw className="h-4 w-4" />
                          )}
                          {current.status === "PROCESSING" ? "Retry if stuck" : "Retry processing"}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </div>
              </Panel>

              <Panel title="AI Decision Trace">
                <div className="relative min-h-[280px]">
                  {isGenerating ? <GenerationOverlay /> : null}
                  <div className={cn("grid gap-6 lg:grid-cols-[1.1fr_0.9fr]", isGenerating && "opacity-35")}>
                    <div className="space-y-5">
                      <TextBlock label="Strategy summary" value={trace.summary} />
                      <TextBlock label="Selected strategy" value={trace.selected_strategy} />
                      <TextBlock label="Audience assessment" value={trace.audience_assessment} />
                      <TextBlock label="CTA rationale" value={trace.why_this_cta} />
                    </div>
                    <div className="space-y-5">
                      <div>
                        <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">
                          Lead signals used
                        </div>
                        <ChipList values={getStringArray(trace.lead_signals_used)} />
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">
                          Personalization used
                        </div>
                        <ChipList values={getStringArray(trace.personalization_used)} />
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">
                          Risks and alternatives
                        </div>
                        <ChipList
                          values={[
                            ...getStringArray(trace.risk_flags),
                            ...getStringArray(trace.alternatives_considered)
                          ]}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-5 lg:grid-cols-2">
                <Panel title="Quality Checks">
                  <div className="space-y-1">
                    <BooleanCheck label="Personalized" value={checks.is_personalized} />
                    <BooleanCheck label="Clear CTA" value={checks.has_clear_cta} />
                    <BooleanCheck label="Tone aligned" value={checks.tone_matches_guidance} />
                    <BooleanCheck label="Sensitive data" value={checks.includes_sensitive_data} />
                    <BooleanCheck label="Unverified claims" value={checks.mentions_unverified_claims} />
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-sm">
                    <AlertTriangle className="h-4 w-4 text-amber" />
                    <span className="font-semibold">Hallucination risk:</span>
                    <span>{checks.hallucination_risk ?? "unknown"}</span>
                  </div>
                  <div className="mt-4">
                    <ChipList values={getStringArray(checks.notes)} />
                  </div>
                </Panel>

                <Panel title="Generation Runs">
                  {(runs.data?.items ?? []).length ? (
                    <div className="space-y-3">
                      {runs.data?.items.slice(0, 4).map((run) => (
                        <div key={run.id} className="border-b border-line/70 pb-3 last:border-0 last:pb-0">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 text-sm font-bold text-ink">
                              <FileText className="h-4 w-4 text-moss" />
                              {humanize(run.request_type)}
                            </div>
                            <Badge className="border-line bg-white text-[#64748b]">{humanize(run.status)}</Badge>
                          </div>
                          <div className="mt-2 text-xs leading-5 text-[#64748b]">
                            {run.latency_ms ?? 0}ms · {formatDate(run.created_at)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="No generation runs" />
                  )}
                </Panel>
              </div>

              <Panel title="Audit Timeline">
                {(audit.data?.items ?? []).length ? (
                  <div className="space-y-3">
                    {audit.data?.items.map((entry) => (
                      <div key={entry.id} className="flex gap-3 border-b border-line/70 pb-3 last:border-0 last:pb-0">
                        <Clock3 className="mt-0.5 h-4 w-4 text-moss" />
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-ink">{humanize(entry.action)}</div>
                          <div className="mt-1 text-xs text-[#64748b]">
                            {entry.actor_name ?? "System"} · {formatDate(entry.created_at)}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No audit entries" />
                )}
              </Panel>
            </div>

            <aside className="space-y-5">
              <Panel title="Lead Context">
                <ContextSection title="Contact" icon={<UserRound className="h-4 w-4 text-moss" />}>
                  <dl>
                    <FieldRow label="Name" value={current.lead_name} />
                    <FieldRow label="Title" value={current.lead_title ?? contact.title} />
                    <FieldRow label="Seniority" value={contact.seniority} />
                    <FieldRow label="Department" value={contact.department} />
                    <FieldRow label="Timezone" value={contact.timezone} />
                  </dl>
                  <div className="mt-4 flex flex-wrap gap-2 text-sm">
                    <Badge className="border-line bg-white text-[#64748b]">
                      <Mail className="h-3.5 w-3.5" />
                      <span className="ml-1.5">{current.lead_email}</span>
                    </Badge>
                    {contact.phone ? (
                      <Badge className="border-line bg-white text-[#64748b]">
                        <Phone className="h-3.5 w-3.5" />
                        <span className="ml-1.5">{contact.phone}</span>
                      </Badge>
                    ) : null}
                  </div>
                </ContextSection>

                <ContextSection title="Company" icon={<Building2 className="h-4 w-4 text-moss" />}>
                  <dl>
                    <FieldRow label="Company" value={company.name ?? current.company_name} />
                    <FieldRow label="Domain" value={company.domain ?? current.company_domain} />
                    <FieldRow label="Industry" value={company.industry} />
                    <FieldRow label="Size" value={company.size_band} />
                    <FieldRow label="Region" value={company.region} />
                    <FieldRow label="Business model" value={company.business_model} />
                    <FieldRow label="Funding" value={company.funding_stage} />
                  </dl>
                  <div className="mt-4">
                    <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Tech stack</div>
                    <ChipList values={company.tech_stack ?? []} />
                  </div>
                </ContextSection>

                <ContextSection title="Source Signal" icon={<Activity className="h-4 w-4 text-moss" />}>
                  <dl>
                    <FieldRow label="Source" value={signal.source ?? current.lead_source} />
                    <FieldRow label="Event" value={signal.event_type ?? current.source_event_type} />
                    <FieldRow label="Event time" value={formatDate(signal.event_at ?? current.source_event_at)} />
                    <FieldRow label="UTM source" value={signal.utm_source} />
                    <FieldRow label="UTM campaign" value={signal.utm_campaign} />
                  </dl>
                  <div className="mt-4 space-y-4">
                    <TextBlock label="Summary" value={signal.summary ?? current.source_event_summary} />
                    <TextBlock label="Raw message" value={signal.raw_message} />
                  </div>
                </ContextSection>

                <ContextSection title="Qualification" icon={<AlertTriangle className="h-4 w-4 text-moss" />}>
                  <div className="mb-5 grid gap-4">
                    <ScoreBar label="Intent score" value={current.intent_score} />
                    <ScoreBar label="Fit score" value={current.fit_score} />
                  </div>
                  <dl>
                    <FieldRow label="Buying stage" value={qualification.buying_stage ?? current.buying_stage} />
                    <FieldRow label="Urgency" value={qualification.urgency} />
                    <FieldRow label="Offer" value={qualification.recommended_offer} />
                  </dl>
                  <div className="mt-4 space-y-4">
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Pain points</div>
                      <ChipList values={qualification.pain_points ?? []} />
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Outcomes</div>
                      <ChipList values={qualification.desired_outcomes ?? []} />
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Objections</div>
                      <ChipList values={qualification.objections ?? []} />
                    </div>
                  </div>
                </ContextSection>

                <ContextSection
                  title="Conversation"
                  icon={<Clock3 className="h-4 w-4 text-moss" />}
                  defaultOpen={false}
                >
                  <div className="space-y-4">
                    <TextBlock label="Last interaction" value={conversation.last_interaction_summary} />
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Preferences</div>
                      <ChipList values={conversation.known_preferences ?? []} />
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Do not mention</div>
                      <ChipList values={conversation.do_not_mention ?? []} />
                    </div>
                    <FieldRow label="Tone guidance" value={conversation.tone_guidance} />
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">
                        Previous touchpoints
                      </div>
                      <Touchpoints values={conversation.previous_touchpoints} />
                    </div>
                  </div>
                </ContextSection>

                <ContextSection
                  title="Personalization"
                  icon={<Sparkles className="h-4 w-4 text-moss" />}
                  defaultOpen={false}
                >
                  <div className="space-y-4">
                    <TextBlock label="Opening angle" value={personalization.opening_angle} />
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">
                        Relevance hooks
                      </div>
                      <ChipList values={personalization.relevance_hooks ?? []} />
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold uppercase tracking-wide text-[#64748b]">Proof points</div>
                      <ChipList values={personalization.proof_points ?? []} />
                    </div>
                    <FieldRow label="CTA type" value={personalization.cta_type} />
                    <TextBlock label="Suggested CTA" value={personalization.suggested_cta} />
                  </div>
                </ContextSection>

                <ContextSection title="CRM" icon={<RefreshCw className="h-4 w-4 text-moss" />} defaultOpen={false}>
                  <dl>
                    <FieldRow label="External ID" value={crm.external_lead_id} />
                    <FieldRow label="Owner" value={crm.owner_name} />
                    <FieldRow label="Lifecycle" value={crm.lifecycle_stage} />
                    <FieldRow label="Last touch" value={formatDate(crm.last_touch_at)} />
                  </dl>
                  <div className="mt-4">
                    <TextBlock label="Next best action" value={crm.next_best_action} />
                  </div>
                </ContextSection>
              </Panel>

              <Panel title="Processing History">
                {current.background_jobs.length ? (
                  <div className="space-y-3">
                    {current.background_jobs.map((job) => (
                      <div key={job.id} className="border-b border-line/70 pb-3 last:border-0 last:pb-0">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 text-sm font-bold text-ink">
                            <RefreshCw className="h-4 w-4 text-moss" />
                            {job.task_name}
                          </div>
                          <Badge className="border-line bg-white text-[#64748b]">{humanize(job.status)}</Badge>
                        </div>
                        <div className="mt-2 text-xs text-[#64748b]">
                          Attempt {job.attempt_count}/{job.max_attempts} · {formatDate(job.created_at)}
                        </div>
                        {job.error_message ? (
                          <div className="mt-2 text-xs font-semibold text-[#be123c]">{job.error_message}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No processing jobs" />
                )}
              </Panel>
            </aside>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
