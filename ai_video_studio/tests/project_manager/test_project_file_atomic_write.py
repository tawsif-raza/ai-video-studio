import threading

from config import settings
from project_manager.manager import ProjectManager


def test_concurrent_reads_never_see_a_partial_project_file(tmp_path, monkeypatch):
    """Regression: project.json was written with a truncate-then-write
    write_text(), so a request reading it while a background run advanced
    state could get an empty file and fail with JSONDecodeError (seen as
    intermittent failures in the API director/producer integration tests).
    Hammer one project with writes while a second thread keeps loading it."""
    monkeypatch.setattr(settings, "OUTPUT_DIR", tmp_path)
    manager = ProjectManager()
    project = manager.create_project(owner_user_id="user-1")

    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        current = project
        while not stop.is_set():
            current = current.model_copy()
            manager._write_project_file(current)

    def reader() -> None:
        for _ in range(2000):
            try:
                manager.load_project(project.project_id, owner_user_id="user-1")
            except BaseException as exc:  # noqa: BLE001 - surface any failure
                errors.append(exc)
                break
        stop.set()

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, f"reader observed a partial project.json: {errors[0]!r}"
    leftovers = list((tmp_path / "projects" / project.project_id).glob(".project.*.tmp"))
    assert leftovers == []
