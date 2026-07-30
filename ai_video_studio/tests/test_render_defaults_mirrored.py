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
preset than expected was needed, not just a lighter one than "medium".

RenderOptions' default is mirrored, by explicit documented convention
(web_api/models.py's RenderRunRequest docstring), across three places that
must never drift apart - which is exactly the failure mode that let this
defect ship unnoticed via one of them. This test pins all three together so a
future change to only one is caught immediately, rather than silently
reintroducing the crash through whichever entry point wasn't updated."""

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
