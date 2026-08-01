import uuid

from web_api.dependencies import get_project_manager


def test_upload_media_unknown_project_returns_404(client):
    response = client.post(
        f"/projects/{uuid.uuid4()}/media",
        files={"file": ("shot1.png", b"content", "image/png")},
    )

    assert response.status_code == 404


def test_upload_media_saves_and_is_visible_via_get(client, app_):
    project = get_project_manager().create_project()

    upload_response = client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("shot1.png", b"x" * 100, "image/png")},
    )

    assert upload_response.status_code == 201
    body = upload_response.json()
    assert body["filename"] == "shot1.png"
    assert body["size_bytes"] == 100
    assert body["path"].endswith("shot1.png")

    media_response = client.get(f"/projects/{project.project_id}/media")

    assert media_response.status_code == 200
    manifest = media_response.json()
    assert [f["filename"] for f in manifest["images"]] == ["shot1.png"]
    assert manifest["videos"] == []
    assert manifest["audio"] == []


def test_upload_media_routes_video_and_audio_correctly(client, app_):
    project = get_project_manager().create_project()

    client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("clip1.mp4", b"x" * 50, "video/mp4")},
    )
    client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("narration.wav", b"x" * 50, "audio/wav")},
    )

    manifest = client.get(f"/projects/{project.project_id}/media").json()

    assert [f["filename"] for f in manifest["videos"]] == ["clip1.mp4"]
    assert [f["filename"] for f in manifest["audio"]] == ["narration.wav"]
    assert manifest["images"] == []


def test_upload_media_rejects_unsupported_extension(client, app_):
    project = get_project_manager().create_project()

    response = client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("malware.exe", b"content", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_get_media_unknown_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}/media")

    assert response.status_code == 404


def test_get_media_empty_when_nothing_uploaded(client, app_):
    project = get_project_manager().create_project()

    response = client.get(f"/projects/{project.project_id}/media")

    assert response.status_code == 200
    assert response.json() == {"images": [], "videos": [], "audio": []}


def test_delete_media_removes_file_and_returns_204(client, app_):
    project = get_project_manager().create_project()
    client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("shot1.png", b"x" * 100, "image/png")},
    )

    response = client.delete(f"/projects/{project.project_id}/media/images/shot1.png")

    assert response.status_code == 204
    manifest = client.get(f"/projects/{project.project_id}/media").json()
    assert manifest["images"] == []


def test_delete_media_unknown_project_returns_404(client):
    response = client.delete(f"/projects/{uuid.uuid4()}/media/images/shot1.png")

    assert response.status_code == 404


def test_delete_media_unknown_file_returns_404(client, app_):
    project = get_project_manager().create_project()

    response = client.delete(f"/projects/{project.project_id}/media/images/nope.png")

    assert response.status_code == 404


def test_delete_media_rejects_invalid_category(client, app_):
    project = get_project_manager().create_project()

    response = client.delete(f"/projects/{project.project_id}/media/documents/nope.png")

    assert response.status_code == 422


def test_bulk_delete_media_reports_per_item_success_and_failure(client, app_):
    project = get_project_manager().create_project()
    client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("shot1.png", b"x" * 100, "image/png")},
    )
    client.post(
        f"/projects/{project.project_id}/media",
        files={"file": ("shot2.png", b"x" * 100, "image/png")},
    )

    response = client.post(
        f"/projects/{project.project_id}/media/bulk-delete",
        json={
            "items": [
                {"category": "images", "filename": "shot1.png"},
                {"category": "images", "filename": "shot2.png"},
                {"category": "images", "filename": "does-not-exist.png"},
            ]
        },
    )

    assert response.status_code == 200
    results = {r["filename"]: r for r in response.json()["results"]}
    assert results["shot1.png"]["success"] is True
    assert results["shot2.png"]["success"] is True
    assert results["does-not-exist.png"]["success"] is False
    assert results["does-not-exist.png"]["error"]

    manifest = client.get(f"/projects/{project.project_id}/media").json()
    assert manifest["images"] == []


def test_bulk_delete_media_unknown_project_returns_404(client):
    response = client.post(
        f"/projects/{uuid.uuid4()}/media/bulk-delete",
        json={"items": [{"category": "images", "filename": "shot1.png"}]},
    )

    assert response.status_code == 404


def test_bulk_delete_media_empty_items_returns_empty_results(client, app_):
    project = get_project_manager().create_project()

    response = client.post(f"/projects/{project.project_id}/media/bulk-delete", json={"items": []})

    assert response.status_code == 200
    assert response.json() == {"results": []}
