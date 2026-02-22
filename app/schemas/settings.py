"""Settings: profile and workspace update schemas."""

from typing import Optional
from pydantic import BaseModel


class MeUpdateRequest(BaseModel):
    name: Optional[str] = None
