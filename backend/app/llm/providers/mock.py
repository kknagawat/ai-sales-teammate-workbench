from datetime import UTC, datetime

from app.core.config import Settings
from app.llm.errors import LLMProviderError
from app.llm.types import GenerationContext, ProviderGenerationResult
from app.models.enums import LLMProvider, LLMProviderMode
from app.schemas.generation import AIDecisionTrace, AIQualityChecks, GenerationResult


class MockLLMProvider:
    provider = LLMProvider.MOCK
    provider_mode = LLMProviderMode.MOCK
    model = "mock-sales-followup-v1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate_followup(self, context: GenerationContext) -> ProviderGenerationResult:
        self._maybe_fail(context)
        result = generate_mock_followup(
            context.lead_profile,
            context.reviewer_feedback,
        )
        return ProviderGenerationResult(
            output=result,
            provider=self.provider,
            provider_mode=self.provider_mode,
            model=self.model,
            provider_raw_metadata={
                "runtime": True,
                "provider": self.provider.value,
                "request_type": context.request_type.value,
            },
            token_usage={"input_tokens": 900, "output_tokens": 360},
            latency_ms=25,
        )

    def _maybe_fail(self, context: GenerationContext) -> None:
        mode = self.settings.mock_llm_failure_mode
        if mode == "none":
            return
        if mode == "intermittent":
            should_fail = context.work_item_id.int % 2 == 0
            if not should_fail:
                return
        if mode == "timeout":
            raise TimeoutError("Mock LLM timeout.")
        if mode == "rate_limit":
            raise LLMProviderError("Mock LLM rate limit.")
        if mode == "malformed":
            raise LLMProviderError("Mock LLM returned malformed structured output.")
        raise LLMProviderError("Mock LLM provider error.")


def generate_mock_followup(lead_profile: dict, feedback: str | None = None) -> GenerationResult:
    contact = lead_profile["contact"]
    company = lead_profile["company"]
    qualification = lead_profile["qualification"]
    signal = lead_profile["source_signal"]
    personalization = lead_profile["personalization"]

    body = (
        f"Hi {contact['first_name']},\n\n"
        f"I noticed {company['name']} recently showed interest through {signal['source'].lower()}. "
        f"Given your focus on {qualification['pain_points'][0].lower()}, it may be useful "
        "to look at a reviewer-controlled AI follow-up workflow before your team scales "
        "this further.\n\n"
        "The workflow keeps the AI teammate responsible for drafting and rationale, while the "
        "human reviewer owns approval and final edits.\n\n"
        f"{personalization['suggested_cta']}\n\n"
        "Best,\nMira"
    )
    summary = (
        f"Generated at {datetime.now(UTC).isoformat()} using lead signal, qualification, "
        f"and {'reviewer feedback' if feedback else 'standard review guidance'}."
    )
    return GenerationResult(
        subject=f"Following up on {company['name']}'s review workflow",
        email_body=body,
        preview_text=body.split("\n\n")[1][:140],
        decision_trace=AIDecisionTrace(
            summary=summary,
            selected_strategy="Consultative follow-up with explicit human control.",
            audience_assessment=(
                f"{contact['title']} likely cares about speed, risk, and consistency."
            ),
            buying_stage_assessment=qualification["buying_stage"],
            personalization_used=personalization["relevance_hooks"],
            lead_signals_used=[signal["summary"]],
            pain_points_addressed=qualification["pain_points"],
            objections_handled=qualification["objections"],
            alternatives_considered=["Send a resource", "Ask a discovery question"],
            risk_flags=["Avoid unverified customer claims"],
            why_this_cta=personalization["suggested_cta"],
        ),
        quality_checks=AIQualityChecks(
            is_personalized=True,
            mentions_unverified_claims=False,
            has_clear_cta=True,
            tone_matches_guidance=True,
            includes_sensitive_data=False,
            hallucination_risk="low",
            notes=["Mock generation is deterministic and schema-valid."],
        ),
        recommended_next_action=personalization["suggested_cta"],
        confidence="high" if qualification["intent_score"] >= 80 else "medium",
    )
