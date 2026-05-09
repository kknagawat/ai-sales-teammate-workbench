from fastapi import HTTPException, status


def not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found.")


def conflict(
    message: str = "This item changed. Refresh before continuing.",
    *,
    code: str = "CONFLICT",
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"message": message, "code": code},
    )
