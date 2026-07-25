import pytest

from agents.base.exceptions import ContractViolationError
from agents.thumbnail_planner.contract import ThumbnailPlannerInput
from agents.thumbnail_planner.validator import build_thumbnail_plan
from shared_core.contracts.character_sheet import CharacterSheet, CharacterVisualProfile
from shared_core.contracts.editing_plan import EditingPlan, EditingSegment
from shared_core.contracts.production_plan import CharacterBrief, ProductionPlan, SceneBrief


def _profile(name, reference_prompt=None):
    return CharacterVisualProfile(
        name=name, age_range="mid-20s", build="lean", face_details="warm eyes",
        hair="black hair", outfit="green tunic", color_palette=["green", "brown"],
        distinguishing_features="a faint scar", art_style_keywords=["3D animated", "Pixar-like"],
        reference_prompt=reference_prompt or f"A lean young figure named {name} with warm eyes and black hair.",
    )


def _character_sheet(*profiles):
    return CharacterSheet(character_profiles=list(profiles), source_plan_id="plan-1")


def _production_plan(*, characters=None, scenes=None, title="Crossing", logline="A fox learns road safety.",
                     theme="courage", tone="uplifting"):
    return ProductionPlan(
        title=title, logline=logline, theme=theme, target_duration_seconds=20, tone=tone,
        characters=characters or [CharacterBrief(name="Finnley", role="protagonist", one_line_description="a brave fox")],
        scenes=scenes or [SceneBrief(
            scene_id=1, title="The Road", summary="Finnley approaches", setting="a busy road",
            mood="cautious", characters_present=["Finnley"], estimated_duration_seconds=20,
        )],
        source_idea="road safety",
    )


def _segment(scene_id, shot_id, start, end, asset_type="image"):
    return EditingSegment(
        scene_id=scene_id, shot_id=shot_id, asset_path=f"/i/s{scene_id}s{shot_id}.{asset_type}",
        asset_type=asset_type, start_time=start, end_time=end, music_cue_scene_id=scene_id,
        transition_in="cut", transition_out="cut",
    )


def _editing_plan(*segments, editing_plan_id="ep-1"):
    return EditingPlan(editing_plan_id=editing_plan_id, segments=list(segments))


def test_single_variant_produced_with_all_strategy_fields():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
        production_plan=_production_plan(),
        character_sheet=_character_sheet(_profile("Finnley")),
    ))

    assert len(plan.variants) == 1
    v = plan.variants[0]
    assert v.variant_id == "variant_1"
    assert v.focal_subject == "Finnley"
    assert v.emotion == "triumphant"  # "uplifting" tone
    assert v.composition
    assert v.strategy
    assert v.source_scene_id == 1
    assert v.source_shot_id == 1


def test_image_prompt_incorporates_reference_prompt_and_story():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
        production_plan=_production_plan(title="Crossing", theme="courage"),
        character_sheet=_character_sheet(_profile("Finnley", reference_prompt="A russet fox with bright amber eyes and a fluffy tail.")),
    ))

    prompt = plan.variants[0].image_prompt
    assert "A russet fox with bright amber eyes and a fluffy tail." in prompt
    assert "Crossing" in prompt
    assert "courage" in prompt
    assert "3D animated" in prompt  # art_style_keywords


def test_focal_segment_is_longest_shot_tiebroken_to_later():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(
            _segment(1, 1, 0.0, 2.0),
            _segment(2, 2, 2.0, 7.0),   # 5s - longest
            _segment(3, 3, 7.0, 12.0),  # also 5s but later -> wins tiebreak
        ),
        production_plan=_production_plan(scenes=[
            SceneBrief(scene_id=1, title="A", summary="s", setting="road", mood="m",
                       characters_present=["Finnley"], estimated_duration_seconds=2),
            SceneBrief(scene_id=2, title="B", summary="s", setting="forest", mood="m",
                       characters_present=["Finnley"], estimated_duration_seconds=5),
            SceneBrief(scene_id=3, title="C", summary="s", setting="hilltop", mood="m",
                       characters_present=["Finnley"], estimated_duration_seconds=5),
        ]),
        character_sheet=_character_sheet(_profile("Finnley")),
    ))

    assert plan.variants[0].source_scene_id == 3
    assert plan.variants[0].source_shot_id == 3
    assert "hilltop" in plan.variants[0].composition  # setting of the chosen scene


def test_protagonist_selected_by_role_not_list_order():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
        production_plan=_production_plan(characters=[
            CharacterBrief(name="Olwen", role="mentor", one_line_description="a wise owl"),
            CharacterBrief(name="Finnley", role="protagonist", one_line_description="a brave fox"),
        ]),
        character_sheet=_character_sheet(_profile("Olwen"), _profile("Finnley")),
    ))

    assert plan.variants[0].focal_subject == "Finnley"


def test_falls_back_to_first_profile_when_protagonist_has_no_matching_bible_entry():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
        production_plan=_production_plan(characters=[
            CharacterBrief(name="Ghost", role="protagonist", one_line_description="unseen"),
        ]),
        character_sheet=_character_sheet(_profile("Olwen")),
    ))

    assert plan.variants[0].focal_subject == "Olwen"


def test_text_safe_areas_present_and_avoid_lower_right():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
        production_plan=_production_plan(),
        character_sheet=_character_sheet(_profile("Finnley")),
    ))

    areas = plan.variants[0].text_safe_areas
    assert len(areas) >= 1
    for area in areas:
        assert 0.0 <= area.x <= 1.0
        assert 0.0 <= area.y <= 1.0
        # no safe area intrudes into the lower-right timestamp corner
        assert not (area.x + area.width > 0.75 and area.y + area.height > 0.85)


def test_emotion_classification_from_tone():
    for tone, expected in [
        ("uplifting", "triumphant"),
        ("tense and dramatic", "intense"),
        ("heartwarming", "heartfelt"),
        ("an exciting adventure", "excited"),
        ("matter-of-fact", "determined"),  # fallback
    ]:
        plan = build_thumbnail_plan(ThumbnailPlannerInput(
            editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
            production_plan=_production_plan(tone=tone, theme="a plain theme"),
            character_sheet=_character_sheet(_profile("Finnley")),
        ))
        assert plan.variants[0].emotion == expected


def test_source_editing_plan_id_recorded():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0), editing_plan_id="ep-XYZ"),
        production_plan=_production_plan(),
        character_sheet=_character_sheet(_profile("Finnley")),
    ))

    assert plan.source_editing_plan_id == "ep-XYZ"


def test_empty_editing_plan_yields_no_variants():
    plan = build_thumbnail_plan(ThumbnailPlannerInput(
        editing_plan=_editing_plan(),
        production_plan=_production_plan(),
        character_sheet=_character_sheet(_profile("Finnley")),
    ))

    assert plan.variants == []


def test_empty_character_bible_rejected_when_segments_exist():
    with pytest.raises(ContractViolationError):
        build_thumbnail_plan(ThumbnailPlannerInput(
            editing_plan=_editing_plan(_segment(1, 1, 0.0, 5.0)),
            production_plan=_production_plan(),
            character_sheet=CharacterSheet(character_profiles=[], source_plan_id="plan-1"),
        ))
