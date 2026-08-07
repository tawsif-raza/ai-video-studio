"""
Structured error hierarchy for the Video Generation Engine (ARCHITECTURE.md
SS25.9). Mirrors execution_engine/errors.py and publishing_engine/errors.py
exactly - kept separate from both because this engine never imports
execution_engine or publishing_engine (SS25.1 rule 1, verified by import
inspection); a shared base class or a cross-import across peer engines would
violate that boundary for no real benefit.

These are raised only for problems discovered before generation can even be
attempted (environment, input contracts, missing media) - everything that
happens once a provider call is actually made is a VideoGenerationResult,
never an exception, exactly like RenderResult/PublishResult.

Reconciliation note: SS25.9 describes MediaAccessError as "reused from
execution_engine/errors.py, same reuse publishing_engine's design already
makes". Checked against the actual repository, publishing_engine/errors.py
never implements that reuse - it only reserves the name in a comment and
defines no MediaAccessError class at all (its real preflight module reports
readiness as a PublishValidationReport, never raises). Importing
execution_engine.errors.MediaAccessError here would satisfy SS25.9's prose
but break SS25.1 rule 1's stricter, structurally-verified boundary ("never
imports execution_engine"). Rule 1 wins: MediaAccessError is defined locally
below, same name and same failure concept, but with no cross-engine import.
"""


class VideoGenerationError(Exception):
    """Base for every Video Generation Engine failure."""


class VideoGenerationEnvironmentError(VideoGenerationError):
    """Credentials are missing/invalid, or the configured provider has no
    registered adapter - a problem with the host/configuration, not the
    project. Raised before any generation is even attempted."""


class MediaAccessError(VideoGenerationError):
    """The seed image (if given) or the output directory is missing,
    unwritable, or otherwise inaccessible. See module docstring for why this
    is a local class rather than an import from execution_engine.errors."""


class VideoGenerationInputError(VideoGenerationError):
    """The generation request references something invalid - e.g. a
    ShotMediaSelection whose scene_id/shot_id isn't present in the loaded
    PromptSet, or a VideoGenerationRequest whose scene_id/shot_id disagrees
    with its own shot_prompt."""
