import re
from typing import List

from agents.publishing_planner.contract import PublishingPlannerInput
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.publishing_metadata import PublishingMetadata, PublishingPlan, YouTubeMetadata

# YouTube caps a video title at 100 characters.
YOUTUBE_TITLE_MAX = 100

# Common English stop-words stripped out before turning story text into
# keywords - they add no search value.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "at",
    "by", "from", "as", "is", "it", "his", "her", "he", "she", "they", "how",
}

# Theme/audience signals that place the video in YouTube's Education category
# rather than the Entertainment default.
_EDUCATION_KEYWORDS = (
    "safety", "learn", "educat", "lesson", "aware", "science", "history",
    "tutorial", "how to", "teach", "school", "kid", "child",
)

# YouTube default visibility for a freshly-planned video: never public. A
# human flips this when they actually choose to publish.
DEFAULT_VISIBILITY = "private"
DEFAULT_LANGUAGE = "en"


def _to_hashtag(phrase: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", phrase)
    return "#" + "".join(word.capitalize() for word in words) if words else ""


def _keywords_from(production_plan: ProductionPlan) -> List[str]:
    """Deduped, order-preserving keyword list drawn from the theme, each
    character's name, and the distinct settings across scenes - the terms a
    viewer would plausibly search."""
    ordered: List[str] = []
    seen = set()

    def add(term: str) -> None:
        cleaned = term.strip().lower()
        if cleaned and cleaned not in seen and cleaned not in _STOPWORDS:
            seen.add(cleaned)
            ordered.append(cleaned)

    for word in production_plan.theme.split():
        add(word)
    for character in production_plan.characters:
        add(character.name)
    for scene in production_plan.scenes:
        add(scene.setting)
    return ordered[:15]


def _hashtags_from(production_plan: ProductionPlan) -> List[str]:
    tags: List[str] = []
    seen = set()
    for source in (production_plan.theme, production_plan.tone):
        tag = _to_hashtag(source)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    for standard in ("#story", "#animation"):
        if standard not in seen:
            seen.add(standard)
            tags.append(standard)
    return tags[:5]


def _category_for(production_plan: ProductionPlan, audience) -> str:
    haystack = " ".join(
        filter(None, [production_plan.theme, production_plan.title, audience or ""])
    ).lower()
    if any(keyword in haystack for keyword in _EDUCATION_KEYWORDS):
        return "Education"
    return "Entertainment"


def _description_for(production_plan: ProductionPlan, hashtags: List[str], audience) -> str:
    character_names = [c.name for c in production_plan.characters]
    if len(character_names) > 1:
        cast = ", ".join(character_names[:-1]) + f" and {character_names[-1]}"
    else:
        cast = character_names[0] if character_names else "an unforgettable cast"

    audience_clause = f" Perfect for {audience}." if audience else ""
    paragraphs = [
        production_plan.logline,
        f"Join {cast} in this {production_plan.tone} story about {production_plan.theme}.{audience_clause}",
        f"Subscribe for more {production_plan.theme} stories.",
        " ".join(hashtags),
    ]
    return "\n\n".join(p for p in paragraphs if p.strip())


def _playlist_for(production_plan: ProductionPlan) -> str:
    return f"{production_plan.theme.strip().title()} Stories"


def build_publishing_plan(input_data: PublishingPlannerInput) -> PublishingPlan:
    """Composes canonical + YouTube-specific publishing metadata from the
    story and Project Metadata - the entry point for Producer Studio's
    Publishing Metadata stage (ARCHITECTURE.md SS6/SS12), the sixth and last
    planning sub-stage before EDIT_PLAN_READY.

    Runs no LLM and calls no publishing API: title/description/keywords/
    hashtags are templated from the ProductionPlan, exactly as Thumbnail
    Planning composed its prompt. No upload, auth, or scheduling happens
    here."""
    production_plan = input_data.production_plan
    audience = input_data.audience

    keywords = _keywords_from(production_plan)
    hashtags = _hashtags_from(production_plan)
    category = _category_for(production_plan, audience)
    description = _description_for(production_plan, hashtags, audience)
    playlist = _playlist_for(production_plan)

    canonical = PublishingMetadata(
        title=production_plan.title,
        description=description,
        keywords=keywords,
        hashtags=hashtags,
        category=category,
        language=DEFAULT_LANGUAGE,
    )
    youtube = YouTubeMetadata(
        title=production_plan.title[:YOUTUBE_TITLE_MAX],
        description=description,
        tags=keywords,
        category=category,
        default_language=DEFAULT_LANGUAGE,
        playlist=playlist,
        visibility=DEFAULT_VISIBILITY,
    )

    return PublishingPlan(
        source_editing_plan_id=input_data.editing_plan.editing_plan_id,
        source_thumbnail_plan_id=input_data.thumbnail_plan.thumbnail_plan_id,
        canonical=canonical,
        youtube=youtube,
    )
