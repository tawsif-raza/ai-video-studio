"""Regression coverage for the Release-Prep rendering-reliability defect
where the default render preset ("medium") pushed a multi-scene 1080p render's
memory footprint past the deployment's 1GB container ceiling, killing ffmpeg
with SIGKILL - reproduced directly against a real 1GB/2vCPU container via
`docker run --memory=1g --cpus=2` (outside this suite; not reproducible on an
ordinary dev/CI machine, which is exactly why it shipped unnoticed). A lighter
preset ("fast") renders the identical resolution/output successfully under the
same constraint (see tests/integration/test_editing_plan_duration_matches_render.py
for the successful-render regression at both 720p and 1080p).

Only "ultrafast" held up: under a realistic concurrent memory footprint
(matching the FastAPI/uvicorn process ffmpeg actually shares the container
with, not an idle container to itself), "fast", "superfast", and even
"veryfast" all still failed the same way in further testing against the real
deployment - a reminder that this ceiling is tight enough that a lighter
preset than expected was needed, not just a lighter one than "medium". Even
with "ultrafast", the same render was observed to occasionally stall
indefinitely against the live deployment instead of failing cleanly (memory
pinned at the container's 1GB ceiling, ~0% CPU, no progress) - a worse
failure mode than a clean SIGKILL, since nothing ever recovers it and it
starves the whole service of memory. RenderOptions.timeout_seconds
(previously None - no timeout at all) now defaults to 120s so ffmpeg_executor's
existing TimeoutExpired handling actually gets a chance to fire and turn a
stall into a clean, reported failure instead of an indefinite hang.

RenderOptions' defaults are mirrored, by explicit documented convention
(web_api/models.py's RenderRunRequest docstring), across the places that must
never drift apart - which is exactly the failure mode that let both defects
ship unnoticed via one of them. RenderRunRequest.timeout_seconds in
particular explicitly defaulted to None even after RenderOptions' own class
default was fixed to 120s: to_render_options() does
RenderOptions(**self.model_dump()), so RenderRunRequest's own None
explicitly overrode RenderOptions' 120 on every real web API request - the
fix had to land in both places, not just the one that looked like the
single source of truth. This test pins all of them together so a future
change to only one is caught immediately, rather than silently
reintroducing the crash (or the hang) through whichever entry point wasn't
updated."""

import re
from pathlib import Path

from shared_core.contracts.render import RenderOptions
from web_api.models import RenderRunRequest

_RENDER_APP_PY = Path(__file__).resolve().parent.parent / "render_app.py"


def test_render_options_default_preset_is_not_medium():
    assert RenderOptions().preset == "ultrafast"


def test_render_run_request_default_preset_matches_render_options():
    assert RenderRunRequest().preset == RenderOptions().preset


def test_render_app_cli_default_preset_matches_render_options():
    source = _RENDER_APP_PY.read_text()
    match = re.search(r'--preset["\']?,\s*default=["\'](\w+)["\']', source)
    assert match, "could not find --preset argparse default in render_app.py"
    assert match.group(1) == RenderOptions().preset


def test_render_options_default_timeout_is_bounded_not_none():
    # Not None: an unbounded render can stall indefinitely at the container's
    # memory ceiling rather than being cleanly killed - see module docstring.
    assert RenderOptions().timeout_seconds is not None
    assert RenderOptions().timeout_seconds > 0


def test_render_app_cli_default_timeout_matches_render_options():
    source = _RENDER_APP_PY.read_text()
    match = re.search(r'--timeout["\']?,\s*type=int,\s*default=(\d+)', source)
    assert match, "could not find --timeout argparse default in render_app.py"
    assert int(match.group(1)) == RenderOptions().timeout_seconds


def test_render_run_request_default_timeout_matches_render_options():
    # RenderRunRequest.timeout_seconds previously defaulted to None even
    # after RenderOptions' own default was fixed - to_render_options() passes
    # every field through explicitly (RenderOptions(**self.model_dump())), so
    # RenderRunRequest's own None silently overrode RenderOptions' 120 on
    # every real web API request. Both must actually match, not just the
    # (insufficient) constructor-level default.
    assert RenderRunRequest().timeout_seconds == RenderOptions().timeout_seconds
    request = RenderRunRequest()
    assert request.to_render_options().timeout_seconds == RenderOptions().timeout_seconds
