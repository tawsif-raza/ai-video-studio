# Canonical definitions live in shared_core/contracts/character_sheet.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.character_planner.schema keep working unchanged.
from shared_core.contracts.character_sheet import CharacterPlannerSchema, CharacterVisualProfile

__all__ = ["CharacterPlannerSchema", "CharacterVisualProfile"]
