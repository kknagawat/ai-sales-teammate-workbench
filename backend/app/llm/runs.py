from datetime import UTC, datetime

from app.llm.types import GenerationContext, LLMProviderProtocol, ProviderGenerationResult
from app.models.enums import LLMRunStatus
from app.models.lead_work_item import LeadWorkItem
from app.models.llm_generation_run import LLMGenerationRun


def create_generation_run(
    item: LeadWorkItem,
    provider: LLMProviderProtocol,
    context: GenerationContext,
) -> LLMGenerationRun:
    return LLMGenerationRun(
        organization_id=item.organization_id,
        work_item_id=item.id,
        provider=provider.provider,
        provider_mode=provider.provider_mode,
        model=provider.model,
        prompt_version=context.prompt_version,
        schema_version=context.schema_version,
        request_type=context.request_type,
        status=LLMRunStatus.STARTED,
        input_snapshot=context.input_snapshot(),
        provider_raw_metadata={},
    )


def apply_generation_success(
    run: LLMGenerationRun,
    result: ProviderGenerationResult,
) -> None:
    structured_output = result.output.model_dump(mode="json")
    run.status = LLMRunStatus.COMPLETED
    run.structured_output = structured_output
    run.decision_trace = result.output.decision_trace.model_dump(mode="json")
    run.provider_raw_metadata = result.provider_raw_metadata
    run.token_usage = result.token_usage
    run.latency_ms = result.latency_ms
    run.provider_thinking_summary = result.provider_thinking_summary
    run.completed_at = datetime.now(UTC)


def apply_generation_failure(run: LLMGenerationRun | None, exc: Exception) -> None:
    if run is None:
        return
    run.status = LLMRunStatus.FAILED
    run.error_message = (str(exc) or "Provider failed.")[:500]
    run.completed_at = datetime.now(UTC)
