# Canonical definitions live in shared_core/contracts/voice_script.py
# (ARCHITECTURE.md SS7). Re-exported here so existing imports of
# agents.voice_script.schema keep working unchanged.
from shared_core.contracts.voice_script import NarrationLine, VoiceScriptSchema

__all__ = ["NarrationLine", "VoiceScriptSchema"]
