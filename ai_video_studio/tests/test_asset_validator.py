import hashlib

from agents.asset_validator.contract import AssetValidatorInput
from agents.asset_validator.validator import validate_assets
from shared_core.contracts.asset_manifest import ImportedMediaManifest, ScannedMediaFile
from shared_core.contracts.prompt_set import PromptSet, ShotPrompt


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _make_prompt_set(shots=((1, 1), (1, 2), (2, 1))) -> PromptSet:
    return PromptSet(
        shots=[
            ShotPrompt(
                scene_id=scene_id,
                shot_id=shot_id,
                duration_seconds=5,
                image_prompt="A" * 45,
                video_motion_prompt="B" * 20,
            )
            for scene_id, shot_id in shots
        ]
    )


def _scanned(filename: str, content: bytes = b"0" * 6000) -> ScannedMediaFile:
    return ScannedMediaFile(
        filename=filename,
        path=f"/fake/media/{filename}",
        size_bytes=len(content),
        sha256=_hash(content),
    )


def _narration(filename: str = "voice_script.wav", content: bytes = b"0" * 6000) -> ScannedMediaFile:
    return _scanned(filename, content)


def test_full_coverage_by_images_and_narration_is_valid():
    prompt_set = _make_prompt_set(shots=((1, 1), (1, 2)))
    media = ImportedMediaManifest(
        images=[_scanned("scene_1_shot_1.png"), _scanned("scene_1_shot_2.png", b"1" * 6000)],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is True
    assert manifest.issues == []
    assert manifest.narration_audio_path == "/fake/media/voice_script.wav"
    assert {(a.scene_id, a.shot_id) for a in manifest.assets} == {(1, 1), (1, 2)}


def test_full_coverage_by_video_is_valid():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(
        videos=[_scanned("scene_1_shot_1.mp4", b"2" * 20000)],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is True
    assert manifest.assets[0].video_path == "/fake/media/scene_1_shot_1.mp4"
    assert manifest.assets[0].image_path is None


def test_missing_shot_detected():
    prompt_set = _make_prompt_set(shots=((1, 1), (1, 2)))
    media = ImportedMediaManifest(images=[_scanned("scene_1_shot_1.png")], audio=[_narration()])

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert any(i.category == "missing" and "shot 2" in i.description for i in manifest.issues)
    covered = {(a.scene_id, a.shot_id): a for a in manifest.assets}
    assert covered[(1, 2)].image_path is None
    assert covered[(1, 2)].video_path is None


def test_duplicate_same_slot_detected():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(
        images=[_scanned("scene_1_shot_1.png", b"a" * 6000), _scanned("scene_1_shot_1.jpg", b"b" * 6000)],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert any(i.category == "duplicate" and "scene 1 shot 1" in i.description.lower() for i in manifest.issues)


def test_cross_slot_hash_duplicate_detected():
    shared_content = b"same-bytes-reused" * 500
    prompt_set = _make_prompt_set(shots=((1, 1), (1, 2)))
    media = ImportedMediaManifest(
        images=[
            _scanned("scene_1_shot_1.png", shared_content),
            _scanned("scene_1_shot_2.png", shared_content),
        ],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert any(
        i.category == "duplicate" and "identical file content" in i.description.lower()
        for i in manifest.issues
    )


def test_naming_violation_detected():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(
        images=[_scanned("scene_1_shot_1.png"), _scanned("random_photo.png", b"z" * 6000)],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert any(i.category == "naming" and "random_photo.png" in i.description for i in manifest.issues)


def test_undersized_file_treated_as_missing():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(
        images=[_scanned("scene_1_shot_1.png", b"tiny")],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert manifest.assets[0].image_path is None
    assert any("corrupt or truncated" in i.description for i in manifest.issues)


def test_narration_missing_detected():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(images=[_scanned("scene_1_shot_1.png")], audio=[])

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert manifest.narration_audio_path is None
    assert any(i.category == "narration" for i in manifest.issues)


def test_narration_duplicate_detected():
    prompt_set = _make_prompt_set(shots=((1, 1),))
    media = ImportedMediaManifest(
        images=[_scanned("scene_1_shot_1.png")],
        audio=[_narration("voice_script.wav", b"x" * 6000), _narration("voice_script.mp3", b"y" * 6000)],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is False
    assert any(i.category == "duplicate" and "narration" in i.description.lower() for i in manifest.issues)
