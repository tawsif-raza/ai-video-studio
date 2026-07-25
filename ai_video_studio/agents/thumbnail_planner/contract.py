from pydantic import BaseModel

from shared_core.contracts.character_sheet import CharacterSheet
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.thumbnail_plan import TextSafeArea, ThumbnailPlan, ThumbnailVariant

__all__ = [
    "CharacterSheet", "EditingPlan", "ProductionPlan", "TextSafeArea", "ThumbnailPlan",
    "ThumbnailPlannerInput", "ThumbnailVariant",
]


class ThumbnailPlannerInput(BaseModel):
    """Typed input assembled by Project Manager: the just-built EditingPlan
    (to choose which scene/shot the thumbnail draws from), plus the story and
    Character Bible reconstructed from disk. ProductionPlan carries both the
    story fields (title/logline/theme/tone) and the character roles used to
    identify the protagonist by name in the CharacterSheet."""

    editing_plan: EditingPlan
    production_plan: ProductionPlan
    character_sheet: CharacterSheet
