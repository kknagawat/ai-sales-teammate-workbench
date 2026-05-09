from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LeadContact(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    title: str | None = None
    seniority: Literal["IC", "MANAGER", "DIRECTOR", "VP", "CXO", "FOUNDER"]
    department: str
    linkedin_url: str | None = None
    timezone: str


class LeadCompany(BaseModel):
    name: str
    domain: str | None = None
    industry: str
    size_band: Literal["1-10", "11-50", "51-200", "201-1000", "1000+"]
    region: str
    funding_stage: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    business_model: Literal["B2B", "B2C", "Marketplace", "Agency", "Other"]


class LeadSignal(BaseModel):
    source: Literal[
        "Website",
        "Demo Request",
        "Webinar",
        "Event",
        "Referral",
        "Product Signup",
        "CRM Import",
        "Intent Data",
    ]
    event_type: Literal[
        "DemoRequested",
        "PricingViewed",
        "CompetitorCompared",
        "WebinarAttended",
        "ProductSignup",
        "ReferralIntro",
        "HighIntentVisit",
        "Reengagement",
    ]
    event_at: datetime
    summary: str
    raw_message: str
    utm_source: str | None = None
    utm_campaign: str | None = None


class LeadQualification(BaseModel):
    buying_stage: Literal["Awareness", "Consideration", "Evaluation", "ReadyToBuy", "Expansion"]
    intent_score: int = Field(ge=0, le=100)
    fit_score: int = Field(ge=0, le=100)
    urgency: Literal["Low", "Medium", "High"]
    pain_points: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    recommended_offer: str


class PreviousTouchpoint(BaseModel):
    channel: str
    occurred_at: datetime
    summary: str


class LeadConversationContext(BaseModel):
    last_interaction_summary: str
    known_preferences: list[str] = Field(default_factory=list)
    previous_touchpoints: list[PreviousTouchpoint] = Field(default_factory=list)
    do_not_mention: list[str] = Field(default_factory=list)
    tone_guidance: Literal["Concise", "Warm", "Consultative", "Executive", "Technical"]


class LeadPersonalization(BaseModel):
    opening_angle: str
    relevance_hooks: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    cta_type: Literal["BookMeeting", "ReplyWithContext", "ViewResource", "ConfirmInterest"]
    suggested_cta: str


class LeadCRM(BaseModel):
    external_lead_id: str
    owner_name: str
    lifecycle_stage: str
    last_touch_at: datetime | None = None
    next_best_action: str


class LeadProfile(BaseModel):
    contact: LeadContact
    company: LeadCompany
    source_signal: LeadSignal
    qualification: LeadQualification
    conversation_context: LeadConversationContext
    personalization: LeadPersonalization
    crm: LeadCRM
