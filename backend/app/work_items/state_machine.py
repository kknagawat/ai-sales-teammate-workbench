from enum import StrEnum

from app.models.enums import WorkItemStatus


class WorkItemAction(StrEnum):
    EDIT_DRAFT = "EDIT_DRAFT"
    REGENERATE = "REGENERATE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETRY_PROCESSING = "RETRY_PROCESSING"


VALID_TRANSITIONS: dict[WorkItemStatus, set[WorkItemStatus]] = {
    WorkItemStatus.PENDING_REVIEW: {
        WorkItemStatus.REGENERATING,
        WorkItemStatus.PROCESSING,
        WorkItemStatus.REJECTED,
    },
    WorkItemStatus.REGENERATING: {WorkItemStatus.PENDING_REVIEW},
    WorkItemStatus.PROCESSING: {WorkItemStatus.SENT, WorkItemStatus.FAILED},
    WorkItemStatus.FAILED: {
        WorkItemStatus.PROCESSING,
        WorkItemStatus.REGENERATING,
        WorkItemStatus.REJECTED,
    },
    WorkItemStatus.SENT: set(),
    WorkItemStatus.REJECTED: set(),
}

VALID_ACTIONS: dict[WorkItemStatus, set[WorkItemAction]] = {
    WorkItemStatus.PENDING_REVIEW: {
        WorkItemAction.EDIT_DRAFT,
        WorkItemAction.REGENERATE,
        WorkItemAction.APPROVE,
        WorkItemAction.REJECT,
    },
    WorkItemStatus.FAILED: {
        WorkItemAction.EDIT_DRAFT,
        WorkItemAction.REGENERATE,
        WorkItemAction.APPROVE,
        WorkItemAction.REJECT,
        WorkItemAction.RETRY_PROCESSING,
    },
    WorkItemStatus.REGENERATING: set(),
    WorkItemStatus.PROCESSING: {WorkItemAction.RETRY_PROCESSING},
    WorkItemStatus.SENT: set(),
    WorkItemStatus.REJECTED: set(),
}


def can_transition(from_status: WorkItemStatus, to_status: WorkItemStatus) -> bool:
    return to_status in VALID_TRANSITIONS[from_status]


def can_perform_action(status: WorkItemStatus, action: WorkItemAction) -> bool:
    return action in VALID_ACTIONS[status]
