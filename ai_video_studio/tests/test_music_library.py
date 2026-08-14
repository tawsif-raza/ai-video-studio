import json

from execution_engine.music_library import (
    MusicLibraryEntry,
    load_library_index,
    resolve_music_asset,
    verify_music_asset_exists,
)
from shared_core.contracts.music_plan import DuckWindow, MusicCue, MusicPlan


def _cue(scene_id, start, end, *, mood="calm", tempo="slow", intensity="low", is_silent=False):
    return MusicCue(
        scene_id=scene_id, start_time=start, end_time=end, mood=mood, tempo=tempo, intensity=intensity,
        is_silent=is_silent,
    )


def _plan(*cues):
    return MusicPlan(music_plan_id="mp1", source_timeline_id="tl1", cues=list(cues))


def _entry(mood, tempo, intensity, path="track.wav"):
    return MusicLibraryEntry(path=path, mood=mood, tempo=tempo, intensity=intensity)


# ---- resolve_music_asset ----

def test_exact_mood_tempo_intensity_match_wins():
    plan = _plan(_cue(1, 0.0, 5.0, mood="calm", tempo="slow", intensity="low"))
    library = [
        _entry("calm", "slow", "low", path="exact.wav"),
        _entry("calm", "slow", "medium", path="tempo_only.wav"),
    ]
    assert resolve_music_asset(plan, library) == "exact.wav"


def test_falls_back_to_mood_and_tempo_when_no_exact_intensity_match():
    plan = _plan(_cue(1, 0.0, 5.0, mood="calm", tempo="slow", intensity="high"))  # "high" not in library
    library = [_entry("calm", "slow", "low", path="mood_tempo.wav")]
    assert resolve_music_asset(plan, library) == "mood_tempo.wav"


def test_falls_back_to_mood_only_when_no_tempo_match():
    plan = _plan(_cue(1, 0.0, 5.0, mood="calm", tempo="fast", intensity="low"))
    library = [_entry("calm", "slow", "low", path="mood_only.wav")]
    assert resolve_music_asset(plan, library) == "mood_only.wav"


def test_no_match_returns_none_never_raises():
    plan = _plan(_cue(1, 0.0, 5.0, mood="tense", tempo="fast", intensity="high"))
    library = [_entry("calm", "slow", "low")]
    assert resolve_music_asset(plan, library) is None


def test_empty_library_returns_none():
    plan = _plan(_cue(1, 0.0, 5.0))
    assert resolve_music_asset(plan, []) is None


def test_all_silent_cues_returns_none():
    plan = _plan(_cue(1, 0.0, 5.0, is_silent=True), _cue(2, 5.0, 10.0, is_silent=True))
    library = [_entry("neutral", "medium", "medium")]
    assert resolve_music_asset(plan, library) is None


def test_no_cues_returns_none():
    plan = _plan()
    library = [_entry("calm", "slow", "low")]
    assert resolve_music_asset(plan, library) is None


def test_first_non_silent_cue_is_representative():
    # scene 1 is silent, scene 2 is the first cue with actual music - its
    # mood/tempo/intensity should drive the match, not scene 1's.
    plan = _plan(
        _cue(1, 0.0, 2.0, is_silent=True),
        _cue(2, 2.0, 8.0, mood="tense", tempo="fast", intensity="high"),
        _cue(3, 8.0, 12.0, mood="calm", tempo="slow", intensity="low"),
    )
    library = [_entry("tense", "fast", "high", path="tense.wav"), _entry("calm", "slow", "low", path="calm.wav")]
    assert resolve_music_asset(plan, library) == "tense.wav"


def test_deterministic_across_calls():
    plan = _plan(_cue(1, 0.0, 5.0, mood="calm", tempo="slow", intensity="low"))
    library = [_entry("calm", "slow", "low", path="a.wav")]
    assert resolve_music_asset(plan, library) == resolve_music_asset(plan, library)


# ---- load_library_index (boundary) ----

def test_load_library_index_reads_and_resolves_relative_paths(tmp_path):
    index_path = tmp_path / "library_index.json"
    index_path.write_text(json.dumps({
        "tracks": [{"path": "calm.wav", "mood": "calm", "tempo": "slow", "intensity": "low"}]
    }))
    (tmp_path / "calm.wav").write_bytes(b"x")

    entries = load_library_index(str(index_path))
    assert len(entries) == 1
    assert entries[0].path == str(tmp_path / "calm.wav")
    assert entries[0].mood == "calm"


def test_load_library_index_missing_file_returns_empty_list(tmp_path):
    assert load_library_index(str(tmp_path / "does_not_exist.json")) == []


def test_load_library_index_malformed_json_returns_empty_list(tmp_path):
    index_path = tmp_path / "library_index.json"
    index_path.write_text("{not valid json")
    assert load_library_index(str(index_path)) == []


def test_load_library_index_skips_malformed_entries_keeps_valid_ones(tmp_path):
    index_path = tmp_path / "library_index.json"
    index_path.write_text(json.dumps({
        "tracks": [
            {"path": "ok.wav", "mood": "calm", "tempo": "slow", "intensity": "low"},
            {"mood": "missing_path_field"},
            "not_even_a_dict",
        ]
    }))
    entries = load_library_index(str(index_path))
    assert len(entries) == 1
    assert entries[0].mood == "calm"


def test_default_library_index_loads_the_shipped_placeholder_tracks():
    # Milestone A ships assets/music/library_index.json + 2 placeholder
    # tone files so the pipeline is testable before real tracks are sourced.
    entries = load_library_index()
    assert len(entries) >= 1
    for entry in entries:
        assert verify_music_asset_exists(entry.path)


# ---- verify_music_asset_exists (boundary) ----

def test_verify_music_asset_exists_true_for_real_file(tmp_path):
    f = tmp_path / "track.wav"
    f.write_bytes(b"x")
    assert verify_music_asset_exists(str(f)) is True


def test_verify_music_asset_exists_false_for_missing_file(tmp_path):
    assert verify_music_asset_exists(str(tmp_path / "nope.wav")) is False
