from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class SocialAccountResponse(BaseModel):
    id: UUID
    workspaceId: UUID = Field(alias="workspace_id", serialization_alias="workspaceId")
    platform: str
    displayName: Optional[str] = Field(None, alias="display_name", serialization_alias="displayName")
    username: Optional[str] = None
    avatarUrl: Optional[str] = Field(None, alias="avatar_url", serialization_alias="avatarUrl")
    status: str
    createdAt: datetime = Field(alias="created_at", serialization_alias="createdAt")
    updatedAt: datetime = Field(alias="updated_at", serialization_alias="updatedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SocialAccountUpdateRequest(BaseModel):
    displayName: Optional[str] = None
    status: Optional[str] = None


class SocialProviderResponse(BaseModel):
    platform: str
    authUrl: str
    connectUrlPath: str
    displayName: str


class ConnectUrlResponse(BaseModel):
    url: str
