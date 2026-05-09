export type UserRole = "ADMIN" | "REVIEWER";
export type WorkItemStatus =
  | "PENDING_REVIEW"
  | "REGENERATING"
  | "PROCESSING"
  | "SENT"
  | "FAILED"
  | "REJECTED";
export type WorkItemPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type LLMProvider = "anthropic" | "mock";
export type LLMProviderMode = "real" | "mock";
export type LLMRequestType = "INITIAL_DRAFT" | "REGENERATION";
export type LLMRunStatus = "STARTED" | "COMPLETED" | "FAILED";
export type BackgroundJobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";

export type User = {
  id: string;
  organization_id: string;
  email: string;
  name: string;
  role: UserRole;
};

export type AuthResponse = {
  user: User;
};

export type PublicConfig = {
  environment: "local" | "test" | "staging" | "production";
  llm: {
    provider: LLMProvider;
    provider_label: string;
    mode: LLMProviderMode;
    model_label: string;
    structured_outputs_enabled: boolean;
    decision_trace_enabled: boolean;
    provider_thinking_summary_enabled: boolean;
    runtime_switching_enabled: boolean;
    available_providers: LLMProvider[];
    active_provider_source: "environment" | "runtime_override";
    anthropic_configured: boolean;
  };
  features: {
    regeneration: boolean;
    approval_processing: boolean;
    audit_log: boolean;
    ai_decision_trace: boolean;
  };
};

export type AssignedReviewer = {
  id: string;
  name: string;
  email: string;
};

export type WorkItemSummary = {
  id: string;
  status: WorkItemStatus;
  priority: WorkItemPriority;
  version: number;
  lead_name: string;
  lead_email: string;
  lead_title: string | null;
  company_name: string;
  company_domain: string | null;
  lead_source: string;
  source_event_type: string;
  buying_stage: string;
  intent_score: number;
  fit_score: number;
  assigned_reviewer: AssignedReviewer | null;
  created_at: string;
  updated_at: string;
};

export type GenerationRun = {
  id: string;
  provider: LLMProvider;
  provider_mode: LLMProviderMode;
  model: string;
  request_type: LLMRequestType;
  status: LLMRunStatus;
  structured_output: Record<string, unknown> | null;
  decision_trace: DecisionTrace | null;
  token_usage: Record<string, unknown> | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type DecisionTrace = {
  summary?: string;
  selected_strategy?: string;
  audience_assessment?: string;
  buying_stage_assessment?: string;
  personalization_used?: string[];
  lead_signals_used?: string[];
  pain_points_addressed?: string[];
  objections_handled?: string[];
  alternatives_considered?: string[];
  risk_flags?: string[];
  why_this_cta?: string;
};

export type QualityChecks = {
  is_personalized?: boolean;
  mentions_unverified_claims?: boolean;
  has_clear_cta?: boolean;
  tone_matches_guidance?: boolean;
  includes_sensitive_data?: boolean;
  hallucination_risk?: "low" | "medium" | "high";
  notes?: string[];
};

export type BackgroundJob = {
  id: string;
  task_name: string;
  status: BackgroundJobStatus;
  attempt_count: number;
  max_attempts: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type WorkItemDetail = WorkItemSummary & {
  reviewer_note: string | null;
  ai_draft: string;
  final_draft: string;
  regeneration_count: number;
  approved_draft_snapshot: string | null;
  approved_at: string | null;
  sent_at: string | null;
  source_event_summary: string;
  source_event_at: string;
  lead_profile: LeadProfile;
  latest_generation_run: GenerationRun | null;
  background_jobs: BackgroundJob[];
};

export type PreviousTouchpoint = {
  channel?: string;
  summary?: string;
  occurred_at?: string;
};

export type LeadProfile = {
  contact?: {
    first_name?: string;
    last_name?: string;
    email?: string;
    phone?: string | null;
    title?: string | null;
    seniority?: string;
    department?: string;
    linkedin_url?: string | null;
    timezone?: string;
  };
  company?: {
    name?: string;
    domain?: string | null;
    industry?: string;
    size_band?: string;
    region?: string;
    funding_stage?: string | null;
    tech_stack?: string[];
    business_model?: string;
  };
  source_signal?: {
    source?: string;
    event_type?: string;
    event_at?: string;
    summary?: string;
    raw_message?: string;
    utm_source?: string | null;
    utm_campaign?: string | null;
  };
  qualification?: {
    buying_stage?: string;
    intent_score?: number;
    fit_score?: number;
    urgency?: string;
    pain_points?: string[];
    desired_outcomes?: string[];
    objections?: string[];
    recommended_offer?: string;
  };
  conversation_context?: {
    last_interaction_summary?: string;
    known_preferences?: string[];
    previous_touchpoints?: PreviousTouchpoint[];
    do_not_mention?: string[];
    tone_guidance?: string;
  };
  personalization?: {
    opening_angle?: string;
    relevance_hooks?: string[];
    proof_points?: string[];
    cta_type?: string;
    suggested_cta?: string;
  };
  crm?: {
    external_lead_id?: string;
    owner_name?: string;
    lifecycle_stage?: string;
    last_touch_at?: string | null;
    next_best_action?: string;
  };
};

export type WorkItemListResponse = {
  items: WorkItemSummary[];
};

export type AuditLog = {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  action: string;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
};

export type AuditLogListResponse = {
  items: AuditLog[];
};

export type GenerationRunListResponse = {
  items: GenerationRun[];
};

export type AdminUser = User & {
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type AdminUsersResponse = {
  items: AdminUser[];
};
