from typing import Dict, List, Optional

from agents.base.exceptions import ContractViolationError
from agents.thumbnail_planner.contract import ThumbnailPlannerInput
from shared_core.contracts.character_sheet import CharacterSheet, CharacterVisualProfile
from shared_core.contracts.editing_plan import EditingSegment
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.thumbnail_plan import TextSafeArea, ThumbnailPlan, ThumbnailVariant

# Standard 16:9 thumbnail text-safe zones, as frame fractions: a title block
# in the upper-left, and a lower-third strip - both deliberately avoiding the
# lower-right corner, where a platform duration stamp is burned in later.
DEFAULT_TEXT_SAFE_AREAS = [
    TextSafeArea(label="title", x=0.04, y=0.06, width=0.56, height=0.30),
    TextSafeArea(label="lower_third", x=0.04, y=0.70, width=0.55, height=0.22),
]

# tone/theme keyword -> the emotional read the thumbnail's focal face should
# convey. First match wins; free-text tone strings aren't a fixed vocabulary,
# so this is a best-effort classifier with a strong neutral fallback.
EMOTION_RULES = [
    (("uplift", "hope", "inspir", "triumph", "victor", "joy", "empower"), "triumphant"),
    (("tense", "dark", "suspense", "danger", "fear", "dramatic", "intense"), "intense"),
    (("warm", "gentle", "heartfelt", "heartwarm", "tender", "touching"), "heartfelt"),
    (("excit", "energetic", "fun", "playful", "thrill", "adventure"), "excited"),
]
DEFAULT_EMOTION = "determined"


def _classify_emotion(*texts: str) -> str:
    haystack = " ".join(texts).lower()
    for keywords, emotion in EMOTION_RULES:
        if any(keyword in haystack for keyword in keywords):
            return emotion
    return DEFAULT_EMOTION


def _choose_focal_segment(segments: List[EditingSegment]) -> EditingSegment:
    """The 'hero' shot: the one the edit lingers on longest (a proxy for the
    moment with the most visual weight), tie-broken toward the later shot
    since a climax usually sits nearer the end than the open."""
    return max(segments, key=lambda s: (s.end_time - s.start_time, s.start_time))


def _find_protagonist_name(production_plan: ProductionPlan) -> Optional[str]:
    for character in production_plan.characters:
        if "protagonist" in character.role.lower():
            return character.name
    return production_plan.characters[0].name if production_plan.characters else None


def _resolve_focal_profile(
    character_sheet: CharacterSheet, protagonist_name: Optional[str]
) -> CharacterVisualProfile:
    if protagonist_name is not None:
        for profile in character_sheet.character_profiles:
            if profile.name == protagonist_name:
                return profile
    return character_sheet.character_profiles[0]


def _scene_setting_by_id(production_plan: ProductionPlan) -> Dict[int, str]:
    return {scene.scene_id: scene.setting for scene in production_plan.scenes}


def build_thumbnail_plan(input_data: ThumbnailPlannerInput) -> ThumbnailPlan:
    """Composes a deterministic thumbnail strategy + generation prompt from
    the editing plan's hero shot, the story, and the Character Bible - the
    entry point for Producer Studio's Thumbnail Planning stage
    (ARCHITECTURE.md SS6/SS12).

    Runs no LLM: the focal subject's reference_prompt is already a paste-ready
    image-generation description (CharacterVisualProfile.reference_prompt),
    so this stage cross-references and templates rather than generating any
    new creative text. No thumbnail image is produced, edited, or published."""
    editing_plan = input_data.editing_plan
    production_plan = input_data.production_plan
    character_sheet = input_data.character_sheet

    if not editing_plan.segments:
        return ThumbnailPlan(source_editing_plan_id=editing_plan.editing_plan_id, variants=[])

    if not character_sheet.character_profiles:
        raise ContractViolationError(
            "Thumbnail Planning requires at least one character profile in the Character Bible "
            "to choose a focal subject"
        )

    focal_segment = _choose_focal_segment(editing_plan.segments)
    protagonist_name = _find_protagonist_name(production_plan)
    focal_profile = _resolve_focal_profile(character_sheet, protagonist_name)
    setting = _scene_setting_by_id(production_plan).get(focal_segment.scene_id, "the story's setting")

    emotion = _classify_emotion(production_plan.tone, production_plan.theme)
    art_style = ", ".join(focal_profile.art_style_keywords) if focal_profile.art_style_keywords else "cinematic"

    composition = (
        f"{focal_profile.name} framed in a tight close-up, right-of-center and facing the viewer, "
        f"against a blurred {setting} backdrop with shallow depth of field; bold negative space "
        f"in the upper-left reserved for the title overlay."
    )
    strategy = f"Protagonist close-up on the {emotion} hero moment (scene {focal_segment.scene_id})"
    image_prompt = (
        f"{composition} {focal_profile.reference_prompt} The expression conveys {emotion}. "
        f"Cinematic YouTube thumbnail for \"{production_plan.title}\": {production_plan.logline} "
        f"Theme of {production_plan.theme}, {production_plan.tone} tone. Style: {art_style}. "
        f"High-contrast, saturated color, dramatic rim lighting, sharp focus on the subject's face, "
        f"leaving clear negative space for overlay text."
    )

    variant = ThumbnailVariant(
        variant_id="variant_1",
        strategy=strategy,
        focal_subject=focal_profile.name,
        emotion=emotion,
        composition=composition,
        image_prompt=image_prompt,
        source_scene_id=focal_segment.scene_id,
        source_shot_id=focal_segment.shot_id,
        text_safe_areas=list(DEFAULT_TEXT_SAFE_AREAS),
    )

    return ThumbnailPlan(source_editing_plan_id=editing_plan.editing_plan_id, variants=[variant])
