# Canonical definitions live in shared_core/contracts/environment_sheet.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.environment_planner.schema keep working unchanged.
from shared_core.contracts.environment_sheet import EnvironmentPlannerSchema, EnvironmentProfile

__all__ = ["EnvironmentPlannerSchema", "EnvironmentProfile"]
