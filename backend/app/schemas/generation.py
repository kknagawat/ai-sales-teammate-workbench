from typing import Literal

from pydantic import BaseModel


class AIDecisionTrace(BaseModel):
    summary: str
    selected_strategy: str
    audience_assessment: str
    buying_stage_assessment: str
    personalization_used: list[str]
    lead_signals_used: list[str]
    pain_points_addressed: list[str]
    objections_handled: list[str]
    alternatives_considered: list[str]
    risk_flags: list[str]
    why_this_cta: str


class AIQualityChecks(BaseModel):
    is_personalized: bool
    mentions_unverified_claims: bool
    has_clear_cta: bool
    tone_matches_guidance: bool
    includes_sensitive_data: bool
    hallucination_risk: Literal["low", "medium", "high"]
    notes: list[str]


class GenerationResult(BaseModel):
    subject: str
    email_body: str
    preview_text: str
    decision_trace: AIDecisionTrace
    quality_checks: AIQualityChecks
    recommended_next_action: str
    confidence: Literal["low", "medium", "high"]
