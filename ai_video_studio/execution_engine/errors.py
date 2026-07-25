"""
Structured error hierarchy for the FFmpeg Execution Engine. Kept separate from
the agents' AgentError tree because the Execution Engine is not an agent and
its failure modes are different in kind: environment (a missing binary), media
access (a vanished file), and input contract problems are all distinguishable
here so the CLI can map each to its own exit code (render_app.py).

These three are raised only for problems discovered before execution can even
be attempted (environment, input contracts, missing media) - everything that
happens once ffmpeg actually runs (non-zero exit, a timeout, a spawn failure)
is deliberately NOT an exception here. ffmpeg_executor.execute() always
returns a structured RenderResult instead, exactly like Asset Validation's
is_valid=False: a failed render is a reportable runtime outcome, not a Python
exception. RenderVerificationError (content verification - duration/stream
correctness) remains undefined until a later milestone adds that check.
"""


class RenderError(Exception):
    """Base for every Execution Engine failure."""


class ExecutionEnvironmentError(RenderError):
    """The ffmpeg binary is missing or not runnable - a problem with the host,
    not the project. Raised before any input is even examined."""


class MediaAccessError(RenderError):
    """A planned media asset (a shot's image/video, or the narration audio) is
    missing or unreadable on disk. Asset Validation approved these paths, but
    the Execution Engine re-verifies existence because media I/O is real and a
    file can move or be deleted after planning."""


class RenderInputError(RenderError):
    """The Producer Package inputs are missing, invalid, or mutually
    inconsistent - e.g. an empty editing plan, a manifest that never passed
    validation, or a subtitle/music plan built from a different timeline than
    the editing plan references."""
