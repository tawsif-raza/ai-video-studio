# Canonical definition lives in shared_core/contracts/research.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.research.schema keep working unchanged.
from shared_core.contracts.research import ResearchSchema

__all__ = ["ResearchSchema"]
