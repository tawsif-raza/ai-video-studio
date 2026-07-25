import pytest

from execution_engine.errors import MediaAccessError
from execution_engine.preflight import verify_media_exists
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderRequest
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline


def _request(image_path, narration_path):
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
