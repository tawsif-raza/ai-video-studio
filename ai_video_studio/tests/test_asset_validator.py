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


def test_missing_shot_within_tolerance_is_still_valid():
    # Release milestone: a shot or two not generated yet is common
    # mid-production and shouldn't block everything else - up to
    # MAX_TOLERATED_MISSING_SHOTS missing shots is tolerated (the Execution
    # Engine renders a plain black frame for each), previously this alone
    # made is_valid False for even a single missing shot.
    prompt_set = _make_prompt_set(shots=((1, 1), (1, 2)))
    media = ImportedMediaManifest(images=[_scanned("scene_1_shot_1.png")], audio=[_narration()])

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.is_valid is True
    assert manifest.missing_shot_count == 1
    assert any(i.category == "missing_shot" and "shot 2" in i.description for i in manifest.issues)
    covered = {(a.scene_id, a.shot_id): a for a in manifest.assets}
    assert covered[(1, 2)].image_path is None
    assert covered[(1, 2)].video_path is None


def test_missing_shots_at_exact_tolerance_boundary_is_valid():
    from agents.asset_validator.validator import MAX_TOLERATED_MISSING_SHOTS

    shots = tuple((1, i) for i in range(1, MAX_TOLERATED_MISSING_SHOTS + 2))
    prompt_set = _make_prompt_set(shots=shots)
    # Only the first shot has media - exactly MAX_TOLERATED_MISSING_SHOTS are missing.
    media = ImportedMediaManifest(images=[_scanned("scene_1_shot_1.png")], audio=[_narration()])

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.missing_shot_count == MAX_TOLERATED_MISSING_SHOTS
    assert manifest.is_valid is True


def test_missing_shots_over_tolerance_blocks_with_clear_count():
    from agents.asset_validator.validator import MAX_TOLERATED_MISSING_SHOTS

    shots = tuple((1, i) for i in range(1, MAX_TOLERATED_MISSING_SHOTS + 3))
    prompt_set = _make_prompt_set(shots=shots)
    media = ImportedMediaManifest(images=[_scanned("scene_1_shot_1.png")], audio=[_narration()])

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    expected_missing = MAX_TOLERATED_MISSING_SHOTS + 1
    assert manifest.missing_shot_count == expected_missing
    assert manifest.is_valid is False
    assert any(
        i.category == "missing_shot" and str(expected_missing) in i.description and "tolerates" in i.description
        for i in manifest.issues
    )


def test_missing_shots_within_tolerance_still_blocked_by_other_issues():
    # Missing-shot coverage is the only category tolerated by count - a
    # naming violation elsewhere must still block regardless of how few
    # shots are missing.
    prompt_set = _make_prompt_set(shots=((1, 1), (1, 2)))
    media = ImportedMediaManifest(
        images=[_scanned("random_photo.png")],
        audio=[_narration()],
    )

    manifest = validate_assets(AssetValidatorInput(prompt_set=prompt_set, imported_media=media))

    assert manifest.missing_shot_count == 2
    assert manifest.is_valid is False
    assert any(i.category == "naming" for i in manifest.issues)


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
