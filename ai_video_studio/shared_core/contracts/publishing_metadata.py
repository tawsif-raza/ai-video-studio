import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class PublishingMetadata(BaseModel):
    """Platform-agnostic canonical metadata - the single source every
    platform-specific block projects from. Keeping this separate from the
    YouTube block is what prepares the plan for future multi-platform
    publishing (responsibility 4): a new platform adds its own projection
    without touching this."""

    title: str
    description: str
    keywords: List[str] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)
    category: str
    language: str


class YouTubeMetadata(BaseModel):
    """YouTube-specific projection of the canonical metadata, plus the upload
    fields that don't generalize across platforms. title is capped to
    YouTube's 100-character limit; tags is YouTube's name for keywords.
    visibility defaults to 'private' upstream - a planning artifact never
    plans to auto-publish publicly; a human promotes it later."""

    title: str
    description: str
    tags: List[str] = Field(default_factory=list)
    category: str
    default_language: str
    playlist: str
    visibility: str  # "public" | "unlisted" | "private"


class PublishingPlan(BaseModel):
    """Public output contract (ARCHITECTURE.md SS6/SS12) - Producer Package's
    publishing_metadata.json. Metadata only: no upload, authentication,
    scheduling, or YouTube API call happens here - those are a later,
    still-unimplemented executor's job."""

    publishing_plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_editing_plan_id: str = ""
    source_thumbnail_plan_id: str = ""
    canonical: PublishingMetadata
    youtube: YouTubeMetadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
