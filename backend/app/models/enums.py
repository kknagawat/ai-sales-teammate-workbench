from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"


class WorkItemStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    REGENERATING = "REGENERATING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class WorkItemPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class LLMProviderMode(StrEnum):
    REAL = "real"
    MOCK = "mock"


class LLMRequestType(StrEnum):
    INITIAL_DRAFT = "INITIAL_DRAFT"
    REGENERATION = "REGENERATION"


class LLMRunStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BackgroundJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
