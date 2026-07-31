import pytest

from execution_engine.command_builder import build_command, validate_render_request
from execution_engine.errors import RenderInputError
from shared_core.contracts.asset_manifest import ValidatedAssetManifest
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.music_plan import MusicPlan
from shared_core.contracts.render import RenderOptions, RenderRequest
from shared_core.contracts.subtitle import SubtitlePlan
from shared_core.contracts.timeline import Timeline


def _segment(scene_id, shot_id, start, end, asset_type="image"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/media/s{scene_id}s{shot_id}.{asset_type}",
        asset_type=asset_type, start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in="cut", transition_out="cut",
    )


def _request(*, segments=None, options=None, output_dir="/out",
             manifest_valid=True, narration="/media/audio/voice_script.wav",
             timeline_id="tl1", manifest_id="m1", subtitle_id="sp1", music_id="mp1",
             ep_timeline_id=None, ep_subtitle_id=None, ep_music_id=None,
             timeline_manifest_id=None, subtitle_timeline_id=None, music_timeline_id=None):
    segments = segments if segments is not None else [_segment(1, 1, 0.0, 2.0), _segment(1, 2, 2.0, 5.0)]
    manifest = ValidatedAssetManifest(
        manifest_id=manifest_id, source_prompt_set_id="ps", is_valid=manifest_valid, narration_audio_path=narration,
    )
    timeline = Timeline(
        timeline_id=timeline_id,
        source_asset_manifest_id=timeline_manifest_id if timeline_manifest_id is not None else manifest_id,
    )
    subtitle_plan = SubtitlePlan(
        subtitle_plan_id=subtitle_id,
        source_timeline_id=subtitle_timeline_id if subtitle_timeline_id is not None else timeline_id,
    )
    music_plan = MusicPlan(
        music_plan_id=music_id,
        source_timeline_id=music_timeline_id if music_timeline_id is not None else timeline_id,
    )
    editing_plan = EditingPlan(
        editing_plan_id="ep1",
        source_timeline_id=ep_timeline_id if ep_timeline_id is not None else timeline_id,
        source_subtitle_plan_id=ep_subtitle_id if ep_subtitle_id is not None else subtitle_id,
        source_music_plan_id=ep_music_id if ep_music_id is not None else music_id,
        segments=segments,
        total_duration_seconds=max((s.end_time for s in segments), default=0.0),
    )
    return RenderRequest(
        editing_plan=editing_plan, asset_manifest=manifest, timeline=timeline,
        subtitle_plan=subtitle_plan, music_plan=music_plan, output_dir=output_dir,
        options=options or RenderOptions(),
    )


# ---- build_command ----

def test_one_input_per_segment_plus_narration_last():
    spec = build_command(_request())
    assert len(spec.inputs) == 3  # 2 segments + narration
    assert spec.inputs[-1].kind == "audio"
    assert spec.inputs[-1].path == "/media/audio/voice_script.wav"


def test_image_segment_gets_loop_and_duration():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 2.0, "image")]))
    assert spec.inputs[0].pre_input_args == ["-loop", "1", "-t", "2"]
    assert spec.inputs[0].duration_seconds == 2.0
    assert spec.inputs[0].scene_id == 1 and spec.inputs[0].shot_id == 1


def test_video_segment_has_no_pre_input_args():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 3.0, "video")]))
    assert spec.inputs[0].pre_input_args == []
    assert spec.inputs[0].kind == "video"


def test_fractional_duration_formatted_compactly():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 2.5, "image")]))
    assert spec.inputs[0].pre_input_args == ["-loop", "1", "-t", "2.5"]


def test_output_args_reflect_options():
    spec = build_command(_request(
        options=RenderOptions(video_codec="libx265", crf=18, preset="slow", fps=24, threads=4)
    ))
    assert "-c:v" in spec.output_args and "libx265" in spec.output_args
    assert "-crf" in spec.output_args and "18" in spec.output_args
    assert "-preset" in spec.output_args and "slow" in spec.output_args
    assert "-r" in spec.output_args and "24" in spec.output_args
    assert "-threads" in spec.output_args and "4" in spec.output_args


def test_output_args_default_to_single_threaded_encode():
    # Release-Prep milestone: production RSS telemetry showed ffmpeg's own
    # peak memory for a 1080p multi-scene render (~860MB) leaves too little
    # headroom in this deployment's 1GB container even at preset="ultrafast" -
    # preset was already at its floor, so RenderOptions.threads (default 1)
    # is the next lever, disabling libx264's frame-parallel per-thread
    # buffers. A silent regression back to auto-detect (0) would reopen the
    # OOM this test exists to guard against.
    spec = build_command(_request())
    assert "-threads" in spec.output_args
    threads_index = spec.output_args.index("-threads")
    assert spec.output_args[threads_index + 1] == "1"


def test_output_path_under_render_dir():
    spec = build_command(_request(output_dir="/projects/x/renders"))
    assert spec.output_path.replace("\\", "/") == "/projects/x/renders/video.mp4"


def test_filter_complex_built_from_editing_plan_since_8_2():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 2.0), _segment(1, 2, 2.0, 5.0)]))
    assert spec.filter_complex is not None
    assert "concat" in spec.filter_complex  # same-scene cut join


def test_output_args_map_filter_graph_output_and_raw_narration():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 2.0)]))
    assert spec.output_args[0] == "-map"
    assert spec.output_args[1].startswith("[") and spec.output_args[1].endswith("]")
    assert spec.output_args[2] == "-map"
    assert spec.output_args[3] == "1:a"  # narration is input index 1 (single visual segment + audio)


def test_to_argv_orders_globals_inputs_filter_output():
    spec = build_command(_request(segments=[_segment(1, 1, 0.0, 2.0, "image")]))
    argv = spec.to_argv("/usr/bin/ffmpeg")
    assert argv[0] == "/usr/bin/ffmpeg"
    assert argv[1:5] == ["-y", "-hide_banner", "-loglevel", "error"]
    assert "-filter_complex" in argv
    assert argv.index("-filter_complex") < argv.index("-map")
    assert "-i" in argv
    assert argv[-1] == spec.output_path


# ---- validate_render_request ----

def test_empty_editing_plan_rejected():
    with pytest.raises(RenderInputError, match="no segments"):
        validate_render_request(_request(segments=[]))


def test_invalid_manifest_rejected():
    with pytest.raises(RenderInputError, match="did not pass validation"):
        validate_render_request(_request(manifest_valid=False))


def test_missing_narration_rejected():
    with pytest.raises(RenderInputError, match="no narration audio"):
        validate_render_request(_request(narration=None))


def test_zero_length_segment_rejected():
    with pytest.raises(RenderInputError, match="non-positive duration"):
        validate_render_request(_request(segments=[_segment(1, 1, 5.0, 5.0)]))


def test_timeline_manifest_mismatch_rejected():
    with pytest.raises(RenderInputError, match="asset manifest"):
        validate_render_request(_request(timeline_manifest_id="DIFFERENT"))


def test_editing_plan_timeline_mismatch_rejected():
    with pytest.raises(RenderInputError, match="not the provided timeline"):
        validate_render_request(_request(ep_timeline_id="DIFFERENT"))


def test_subtitle_plan_timeline_mismatch_rejected():
    with pytest.raises(RenderInputError, match="Subtitle plan"):
        validate_render_request(_request(subtitle_timeline_id="DIFFERENT"))


def test_music_plan_timeline_mismatch_rejected():
    with pytest.raises(RenderInputError, match="Music plan"):
        validate_render_request(_request(music_timeline_id="DIFFERENT"))


def test_editing_plan_subtitle_reference_mismatch_rejected():
    with pytest.raises(RenderInputError, match="subtitle plan"):
        validate_render_request(_request(ep_subtitle_id="DIFFERENT"))


def test_editing_plan_music_reference_mismatch_rejected():
    with pytest.raises(RenderInputError, match="music plan"):
        validate_render_request(_request(ep_music_id="DIFFERENT"))


def test_valid_request_passes():
    validate_render_request(_request())  # should not raise
