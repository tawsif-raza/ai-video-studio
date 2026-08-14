import pytest

from execution_engine.errors import MediaAccessError
from execution_engine.preflight import verify_media_exists
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderRequest
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline


def _request(image_path, narration_path, music_asset_path=None):
    segment = EditingSegment(
        scene_id=1, shot_id=1, asset_path=str(image_path), asset_type="image",
        start_time=0.0, end_time=2.0, music_cue_scene_id=1, transition_in="cut", transition_out="cut",
    )
    manifest = ValidatedAssetManifest(
        manifest_id="m1", source_prompt_set_id="ps", is_valid=True, narration_audio_path=str(narration_path),
    )
    return RenderRequest(
        editing_plan=EditingPlan(
            editing_plan_id="ep1", source_timeline_id="tl1", source_subtitle_plan_id="sp1",
            source_music_plan_id="mp1", segments=[segment], total_duration_seconds=2.0,
        ),
        asset_manifest=manifest,
        timeline=Timeline(timeline_id="tl1", source_asset_manifest_id="m1"),
        subtitle_plan=SubtitlePlan(subtitle_plan_id="sp1", source_timeline_id="tl1"),
        music_plan=MusicPlan(music_plan_id="mp1", source_timeline_id="tl1"),
        output_dir="/out",
        music_asset_path=str(music_asset_path) if music_asset_path is not None else None,
    )


def test_passes_when_all_media_present(tmp_path):
    image = tmp_path / "scene_1_shot_1.png"
    image.write_bytes(b"x" * 100)
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)

    verify_media_exists(_request(image, narration))  # should not raise


def test_raises_when_asset_missing(tmp_path):
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)
    missing_image = tmp_path / "scene_1_shot_1.png"  # never created

    with pytest.raises(MediaAccessError) as exc:
        verify_media_exists(_request(missing_image, narration))
    assert "scene_1_shot_1.png" in str(exc.value)


def test_raises_when_narration_missing(tmp_path):
    image = tmp_path / "scene_1_shot_1.png"
    image.write_bytes(b"x" * 100)
    missing_narration = tmp_path / "voice_script.wav"  # never created

    with pytest.raises(MediaAccessError) as exc:
        verify_media_exists(_request(image, missing_narration))
    assert "voice_script.wav" in str(exc.value)


def test_black_placeholder_segment_skips_file_check(tmp_path):
    # Release milestone: a shot Asset Validation tolerated as missing has no
    # real file at all (asset_path is None) - command_builder synthesizes a
    # black frame for it, so preflight must not try to stat it as a real path.
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)
    segment = EditingSegment(
        scene_id=1, shot_id=1, asset_path=None, asset_type="black",
        start_time=0.0, end_time=2.0, music_cue_scene_id=1, transition_in="cut", transition_out="cut",
    )
    manifest = ValidatedAssetManifest(
        manifest_id="m1", source_prompt_set_id="ps", is_valid=True, narration_audio_path=str(narration),
    )
    request = RenderRequest(
        editing_plan=EditingPlan(
            editing_plan_id="ep1", source_timeline_id="tl1", source_subtitle_plan_id="sp1",
            source_music_plan_id="mp1", segments=[segment], total_duration_seconds=2.0,
        ),
        asset_manifest=manifest,
        timeline=Timeline(timeline_id="tl1", source_asset_manifest_id="m1"),
        subtitle_plan=SubtitlePlan(subtitle_plan_id="sp1", source_timeline_id="tl1"),
        music_plan=MusicPlan(music_plan_id="mp1", source_timeline_id="tl1"),
        output_dir="/out",
    )

    verify_media_exists(request)  # should not raise


# ---- music asset preflight (ARCHITECTURE.md SS21 item 9) ----

def test_no_resolved_music_asset_is_not_checked(tmp_path):
    # music_asset_path=None (no match / no library) must never be treated as
    # a missing-media problem - that's the graceful-degrade path, not an
    # integrity error.
    image = tmp_path / "scene_1_shot_1.png"
    image.write_bytes(b"x" * 100)
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)

    verify_media_exists(_request(image, narration, music_asset_path=None))  # should not raise


def test_passes_when_resolved_music_asset_exists(tmp_path):
    image = tmp_path / "scene_1_shot_1.png"
    image.write_bytes(b"x" * 100)
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)
    music = tmp_path / "calm.wav"
    music.write_bytes(b"m" * 100)

    verify_media_exists(_request(image, narration, music_asset_path=music))  # should not raise


def test_raises_when_resolved_music_asset_missing_same_severity_as_shot_asset(tmp_path):
    image = tmp_path / "scene_1_shot_1.png"
    image.write_bytes(b"x" * 100)
    narration = tmp_path / "voice_script.wav"
    narration.write_bytes(b"a" * 100)
    missing_music = tmp_path / "calm.wav"  # never created

    with pytest.raises(MediaAccessError) as exc:
        verify_media_exists(_request(image, narration, music_asset_path=missing_music))
    assert "calm.wav" in str(exc.value)
