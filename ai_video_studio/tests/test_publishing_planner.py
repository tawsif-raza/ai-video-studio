from agents.publishing_planner.contract import PublishingPlannerInput
from agents.publishing_planner.validator import build_publishing_plan
from shared_core.contracts.editing_plan import EditingPlan
from shared_core.contracts.production_plan import CharacterBrief, ProductionPlan, SceneBrief
from shared_core.contracts.thumbnail_plan import ThumbnailPlan


def _production_plan(*, title="Road Safety Lesson", logline="A fox learns to cross the road safely.",
                     theme="road safety", tone="uplifting", characters=None, scenes=None):
    return ProductionPlan(
        title=title, logline=logline, theme=theme, target_duration_seconds=20, tone=tone,
        characters=characters or [
            CharacterBrief(name="Finnley", role="protagonist", one_line_description="a brave fox"),
            CharacterBrief(name="Olwen", role="mentor", one_line_description="a wise owl"),
        ],
        scenes=scenes or [
            SceneBrief(scene_id=1, title="The Road", summary="Finnley approaches", setting="a busy road",
                       mood="cautious", characters_present=["Finnley"], estimated_duration_seconds=10),
            SceneBrief(scene_id=2, title="The Crossing", summary="Finnley crosses", setting="the crosswalk",
                       mood="triumphant", characters_present=["Finnley", "Olwen"], estimated_duration_seconds=10),
        ],
        source_idea="road safety",
    )


def _input(production_plan=None, audience=None):
    return PublishingPlannerInput(
        editing_plan=EditingPlan(editing_plan_id="ep-1"),
        thumbnail_plan=ThumbnailPlan(thumbnail_plan_id="tp-1", source_editing_plan_id="ep-1"),
        production_plan=production_plan or _production_plan(),
        audience=audience,
    )


def test_canonical_and_youtube_titles_come_from_story():
    plan = build_publishing_plan(_input())
    assert plan.canonical.title == "Road Safety Lesson"
    assert plan.youtube.title == "Road Safety Lesson"


def test_youtube_title_capped_at_100_chars():
    long_title = "A" * 150
    plan = build_publishing_plan(_input(_production_plan(title=long_title)))
    assert len(plan.youtube.title) == 100
    assert plan.canonical.title == long_title  # canonical keeps the full title


def test_keywords_include_theme_and_character_names_deduped():
    plan = build_publishing_plan(_input())
    kws = plan.canonical.keywords
    assert "road" in kws
    assert "safety" in kws
    assert "finnley" in kws
    assert "olwen" in kws
    assert len(kws) == len(set(kws))  # deduped


def test_stopwords_excluded_from_keywords():
    plan = build_publishing_plan(_input(_production_plan(theme="the art of the chase")))
    assert "the" not in plan.canonical.keywords
    assert "of" not in plan.canonical.keywords
    assert "art" in plan.canonical.keywords
    assert "chase" in plan.canonical.keywords


def test_hashtags_derived_from_theme_and_tone():
    plan = build_publishing_plan(_input())
    assert "#RoadSafety" in plan.canonical.hashtags
    assert "#Uplifting" in plan.canonical.hashtags
    assert all(h.startswith("#") for h in plan.canonical.hashtags)


def test_category_is_education_for_safety_theme():
    plan = build_publishing_plan(_input())
    assert plan.canonical.category == "Education"
    assert plan.youtube.category == "Education"


def test_category_defaults_to_entertainment():
    plan = build_publishing_plan(_input(_production_plan(theme="dragons", title="The Dragon's Quest")))
    assert plan.canonical.category == "Entertainment"


def test_category_education_triggered_by_audience():
    plan = build_publishing_plan(_input(
        _production_plan(theme="dragons", title="The Dragon's Quest"),
        audience="children learning to read",
    ))
    assert plan.canonical.category == "Education"


def test_description_includes_logline_cast_and_hashtags():
    plan = build_publishing_plan(_input())
    desc = plan.canonical.description
    assert "A fox learns to cross the road safely." in desc
    assert "Finnley and Olwen" in desc
    assert "#RoadSafety" in desc


def test_description_includes_audience_when_present():
    plan = build_publishing_plan(_input(audience="young children"))
    assert "young children" in plan.canonical.description


def test_youtube_defaults_visibility_private_and_language_en():
    plan = build_publishing_plan(_input())
    assert plan.youtube.visibility == "private"
    assert plan.youtube.default_language == "en"
    assert plan.canonical.language == "en"


def test_youtube_tags_mirror_canonical_keywords():
    plan = build_publishing_plan(_input())
    assert plan.youtube.tags == plan.canonical.keywords


def test_playlist_derived_from_theme():
    plan = build_publishing_plan(_input())
    assert plan.youtube.playlist == "Road Safety Stories"


def test_provenance_ids_recorded():
    plan = build_publishing_plan(_input())
    assert plan.source_editing_plan_id == "ep-1"
    assert plan.source_thumbnail_plan_id == "tp-1"
