# Canonical definition lives in shared_core/contracts/prompt_set.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.prompt_generator.schema keep working unchanged.
from shared_core.contracts.prompt_set import ShotPromptSchema

__all__ = ["ShotPromptSchema"]
