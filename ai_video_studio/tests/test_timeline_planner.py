import pytest

from agents.base.exceptions import ContractViolationError
from agents.timeline_planner.contract import ShotDuration, TimelinePlannerInput
from agents.timeline_planner.validator import build_timeline
from shared_core.contracts.asset_manifest import ValidatedAsset, ValidatedAssetManifest


def _make_manifest(assets, narration_audio_path="/media/audio/voice_script.wav", is_valid=True):
    return ValidatedAssetManifest(
        source_prompt_set_id="abc",
        assets=assets,
        narration_audio_path=narration_audio_path,
        is_valid=is_valid,
    )


def _durations(*entries):
    return [ShotDuration(scene_id=s, shot_id=h, duration_seconds=d) for s, h, d in entries]


def test_clips_ordered_and_cumulative_times():
    manifest = _make_manifest([
        ValidatedAsset(scene_id=2, shot_id=1, image_path="/media/images/scene_2_shot_1.png"),
        ValidatedAsset(scene_id=1, shot_id=2, image_path="/media/images/scene_1_shot_2.png"),
        ValidatedAsset(scene_id=1, shot_id=1, image_path="/media/images/scene_1_shot_1.png"),
    ])
    durations = _durations((1, 1, 10), (1, 2, 5), (2, 1, 8))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    ordered = [(c.scene_id, c.shot_id) for c in timeline.clips]
    assert ordered == [(1, 1), (1, 2), (2, 1)]

    assert timeline.clips[0].start_time == 0
    assert timeline.clips[0].end_time == 10
    assert timeline.clips[1].start_time == 10
    assert timeline.clips[1].end_time == 15
    assert timeline.clips[2].start_time == 15
    assert timeline.clips[2].end_time == 23
    assert timeline.total_duration_seconds == 23


def test_video_preferred_over_image_when_both_present():
    manifest = _make_manifest([
        ValidatedAsset(
            scene_id=1, shot_id=1,
            image_path="/media/images/scene_1_shot_1.png",
            video_path="/media/video/scene_1_shot_1.mp4",
        ),
    ])
    durations = _durations((1, 1, 5))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    assert timeline.clips[0].asset_type == "video"
    assert timeline.clips[0].asset_path == "/media/video/scene_1_shot_1.mp4"


def test_image_only_asset_type_is_image():
    manifest = _make_manifest([
        ValidatedAsset(scene_id=1, shot_id=1, image_path="/media/images/scene_1_shot_1.png"),
    ])
    durations = _durations((1, 1, 5))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    assert timeline.clips[0].asset_type == "image"


def test_shot_with_neither_image_nor_video_resolves_to_black():
    # Release milestone: Asset Validation now tolerates a shot with no
    # image/video at all (up to MAX_TOLERATED_MISSING_SHOTS) rather than
    # blocking is_valid outright - Timeline Planning must still produce a
    # real clip for it, just with no real asset behind it.
    manifest = _make_manifest([
        ValidatedAsset(scene_id=1, shot_id=1, image_path=None, video_path=None),
    ])
    durations = _durations((1, 1, 5))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    assert timeline.clips[0].asset_type == "black"
    assert timeline.clips[0].asset_path is None
    # Still fully sequenced like any other clip - a placeholder shot doesn't
    # get skipped or shrink the timeline.
    assert timeline.clips[0].start_time == 0
    assert timeline.clips[0].end_time == 5


def test_voice_segments_span_each_scenes_clips():
    manifest = _make_manifest([
        ValidatedAsset(scene_id=1, shot_id=1, image_path="/i/s1s1.png"),
        ValidatedAsset(scene_id=1, shot_id=2, image_path="/i/s1s2.png"),
        ValidatedAsset(scene_id=2, shot_id=1, image_path="/i/s2s1.png"),
    ])
    durations = _durations((1, 1, 10), (1, 2, 5), (2, 1, 8))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    segments = {seg.scene_id: seg for seg in timeline.voice_segments}
    assert segments[1].start_time == 0
    assert segments[1].end_time == 15
    assert segments[1].audio_path == "/media/audio/voice_script.wav"
    assert segments[2].start_time == 15
    assert segments[2].end_time == 23


def test_scene_sequencing_preserved_even_if_assets_list_is_scrambled():
    manifest = _make_manifest([
        ValidatedAsset(scene_id=3, shot_id=1, image_path="/i/s3s1.png"),
        ValidatedAsset(scene_id=1, shot_id=1, image_path="/i/s1s1.png"),
        ValidatedAsset(scene_id=2, shot_id=1, image_path="/i/s2s1.png"),
    ])
    durations = _durations((1, 1, 5), (2, 1, 5), (3, 1, 5))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    assert [c.scene_id for c in timeline.clips] == [1, 2, 3]
    assert [seg.scene_id for seg in timeline.voice_segments] == [1, 2, 3]


def test_no_narration_path_yields_no_voice_segments():
    manifest = _make_manifest(
        [ValidatedAsset(scene_id=1, shot_id=1, image_path="/i/s1s1.png")],
        narration_audio_path=None,
    )
    durations = _durations((1, 1, 5))

    timeline = build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))

    assert timeline.voice_segments == []


def test_invalid_manifest_rejected():
    manifest = _make_manifest([ValidatedAsset(scene_id=1, shot_id=1, image_path="/i/s1s1.png")], is_valid=False)
    durations = _durations((1, 1, 5))

    with pytest.raises(ContractViolationError):
        build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))


def test_missing_duration_for_validated_asset_rejected():
    manifest = _make_manifest([ValidatedAsset(scene_id=1, shot_id=1, image_path="/i/s1s1.png")])
    durations = _durations((1, 2, 5))  # wrong shot_id - doesn't cover (1, 1)

    with pytest.raises(ContractViolationError):
        build_timeline(TimelinePlannerInput(asset_manifest=manifest, shot_durations=durations))
