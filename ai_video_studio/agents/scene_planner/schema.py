# Canonical definitions live in shared_core/contracts/storyboard.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.scene_planner.schema keep working unchanged.
from shared_core.contracts.storyboard import ScenePlan, ScenePlannerSchema, ShotBrief

__all__ = ["ScenePlan", "ScenePlannerSchema", "ShotBrief"]
