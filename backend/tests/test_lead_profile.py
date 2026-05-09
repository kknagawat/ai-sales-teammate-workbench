from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.lead_profile import LeadProfile


def valid_lead_profile_payload() -> dict:
    event_at = datetime(2026, 5, 8, 10, 0, tzinfo=UTC)
    return {
        "contact": {
            "first_name": "Avery",
            "last_name": "Shah",
            "email": "avery.shah@example.com",
            "phone": "+1-555-0100",
            "title": "VP Sales",
            "seniority": "VP",
            "department": "Sales",
            "linkedin_url": "https://www.linkedin.com/in/avery-shah-example",
            "timezone": "America/New_York",
        },
        "company": {
            "name": "Northstar Systems",
            "domain": "northstar.example",
            "industry": "SaaS",
            "size_band": "201-1000",
            "region": "North America",
            "funding_stage": "Series C",
            "tech_stack": ["Salesforce", "Gong", "HubSpot"],
            "business_model": "B2B",
        },
        "source_signal": {
            "source": "Demo Request",
            "event_type": "DemoRequested",
            "event_at": event_at,
            "summary": "Requested a demo after reviewing AI sales assistant pages.",
            "raw_message": "We want to learn how AI teammates can help follow up faster.",
            "utm_source": "linkedin",
            "utm_campaign": "ai-sales-demo",
        },
        "qualification": {
            "buying_stage": "Evaluation",
            "intent_score": 88,
            "fit_score": 91,
            "urgency": "High",
            "pain_points": ["Slow lead response", "Manual follow-up QA"],
            "desired_outcomes": ["Faster response times", "Consistent sales messaging"],
            "objections": ["Needs security review"],
            "recommended_offer": "Book a 30-minute workflow mapping call",
        },
        "conversation_context": {
            "last_interaction_summary": "Asked for examples of human-reviewed AI drafts.",
            "known_preferences": ["Concise examples", "Security details"],
            "previous_touchpoints": [
                {
                    "channel": "Website chat",
                    "occurred_at": event_at,
                    "summary": "Asked whether approvals can be audited.",
                }
            ],
            "do_not_mention": ["unverified customer names"],
            "tone_guidance": "Consultative",
        },
        "personalization": {
            "opening_angle": "Tie the note to their demo request and sales QA goals.",
            "relevance_hooks": ["Demo request", "Auditability question"],
            "proof_points": ["Human approval workflow", "Detailed audit trail"],
            "cta_type": "BookMeeting",
            "suggested_cta": "Would Tuesday or Wednesday work for a 30-minute walkthrough?",
        },
        "crm": {
            "external_lead_id": "lead_001",
            "owner_name": "Mira Patel",
            "lifecycle_stage": "Marketing Qualified Lead",
            "last_touch_at": event_at,
            "next_best_action": "Send personalized follow-up with meeting CTA",
        },
    }


def test_lead_profile_accepts_valid_nested_payload() -> None:
    profile = LeadProfile.model_validate(valid_lead_profile_payload())

    assert profile.contact.email == "avery.shah@example.com"
    assert profile.qualification.intent_score == 88


@pytest.mark.parametrize("score_field", ["intent_score", "fit_score"])
def test_lead_profile_rejects_out_of_range_scores(score_field: str) -> None:
    payload = valid_lead_profile_payload()
    payload["qualification"][score_field] = 101

    with pytest.raises(ValidationError):
        LeadProfile.model_validate(payload)
