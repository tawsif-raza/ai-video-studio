from pydantic import BaseModel

from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.storyboard import Storyboard
from shared_core.contracts.voice_script import VoiceScript

__all__ = ["ProductionPlan", "Storyboard", "VoiceScript", "VoiceScriptInput"]


class VoiceScriptInput(BaseModel):
    production_plan: ProductionPlan
    storyboard: Storyboard
