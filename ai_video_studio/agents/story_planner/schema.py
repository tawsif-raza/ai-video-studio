# Canonical definitions live in shared_core/contracts/production_plan.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.story_planner.schema keep working unchanged.
from shared_core.contracts.production_plan import CharacterBrief, SceneBrief, StoryPlanSchema

__all__ = ["CharacterBrief", "SceneBrief", "StoryPlanSchema"]
