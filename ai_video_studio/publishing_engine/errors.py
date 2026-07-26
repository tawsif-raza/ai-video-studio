"""
Structured error hierarchy for the Publishing Engine (ARCHITECTURE.md SS24.7).
Kept separate from execution_engine/errors.py - despite conceptual overlap on
some failure modes - because publishing_engine never imports execution_engine
(SS24.1, rule 1); a shared base class across the two would violate that
boundary for no real benefit.

As of Milestone P1 (Platform Abstraction), only PublishInputError is raised
in practice (by platforms/registry.py, for an unrecognized platform name).
PublishEnvironmentError and MediaAccessError are reserved for the milestone
that adds preflight/authentication (SS24.6 steps 3-4) - deliberately not
added until that code exists, to avoid dead exception classes.
"""


class PublishError(Exception):
    """Base for every Publishing Engine failure."""


class PublishInputError(PublishError):
    """The publish request references something invalid - e.g. an
    unregistered platform name."""
