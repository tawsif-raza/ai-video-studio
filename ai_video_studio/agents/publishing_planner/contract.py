from typing import Optional

from pydantic import BaseModel

from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata
from shared_core.contracts.thumbnail_plan import ThumbnailPlan

__all__ = [
    "EditingPlan", "ProductionPlan", "PublishingMetadata", "PublishingPlan", "PublishingPlannerInput",
    "ThumbnailPlan", "YouTubeMetadata",
]


class PublishingPlannerInput(BaseModel):
    """Typed input assembled by Project Manager: the just-built EditingPlan
    and ThumbnailPlan (recorded as provenance on the terminal artifact), the
    story (ProductionPlan carries title/logline/theme/tone/characters/scenes),
    and audience from the Production Package's own metadata.json - the
    'Project Metadata' input, the one signal that isn't already on the
    ProductionPlan (None when the run never set an audience)."""

    editing_plan: EditingPlan
    thumbnail_plan: ThumbnailPlan
    production_plan: ProductionPlan
    audience: Optional[str] = None
