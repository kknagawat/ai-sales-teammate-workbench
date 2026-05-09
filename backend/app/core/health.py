from typing import Literal

from pydantic import BaseModel


class DependencyHealth(BaseModel):
    status: Literal["ok", "unavailable", "misconfigured"]
    detail: str | None = None
