from __future__ import annotations

from pydantic import BaseModel


class VerifierResult(BaseModel):
    rewards: dict[str, float | int] | None = None
