import pytest

from config import settings


@pytest.fixture(scope="session", autouse=True)
def _isolate_output_dir(tmp_path_factory):
    """Point settings.OUTPUT_DIR at a session temp dir for the whole run.

    Tests that need their own directory still monkeypatch OUTPUT_DIR to
    tmp_path as before. This is the safety net underneath: several
    PipelineExecutor tests never patch it, and some intentionally leave
    timed-out runs finishing on background threads after the test ends,
    so their late writes happen after any per-test monkeypatch has been
    undone. Without this, test runs left project dirs and prompt_set files
    in the developer's real outputs/.
    """
    original = settings.OUTPUT_DIR
    settings.OUTPUT_DIR = tmp_path_factory.mktemp("outputs")
    yield
    settings.OUTPUT_DIR = original
