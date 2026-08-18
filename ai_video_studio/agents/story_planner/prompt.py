from agents.story_planner.contract import StoryPlannerInput

SYSTEM_INSTRUCTION = """You are the Story Planner agent inside an autonomous AI video studio.
Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
Break the story into short scenes (2-15s each) suitable for short-form vertical video.
Total scene duration must be close to the target duration (within ~30%).
Every name in a scene's characters_present must also appear in the top-level characters list.
"""

SCENE_COUNT_DEFAULT_NOTE = (
    "Use your own judgment for how many scenes best tells this story within "
    "the target duration - there is no fixed scene count to hit."
)


def _scene_count_requirement(scene_count: int) -> str:
    return f"""
SCENE COUNT REQUIREMENT (HARD CONSTRAINT)
The user explicitly requested exactly {scene_count} scenes.
This is a HARD constraint, not a suggestion.
You MUST generate exactly {scene_count} scenes - no more, no fewer.
Do not increase, decrease, approximate, normalize, or reinterpret this number.
Do not fall back to any other scene count based on duration or story pacing.
Split the target duration across exactly {scene_count} scenes, adjusting each
scene's estimated_duration_seconds (2-15s each) so the total still stays
close to the target duration.
The final "scenes" array in your JSON output must contain exactly
{scene_count} entries - count them before responding.
"""


def build_story_planner_prompt(input_data: StoryPlannerInput, correction_note: str = "") -> str:
    tone_line = f"Desired tone: {input_data.tone}\n" if input_data.tone else ""
    audience_line = f"Target audience: {input_data.audience}\n" if input_data.audience else ""
    research_line = ""
    if input_data.research_key_facts or input_data.research_considerations:
        facts = "\n".join(f"- {f}" for f in input_data.research_key_facts)
        considerations = "\n".join(f"- {c}" for c in input_data.research_considerations)
        research_line = f"\nBackground research:\n{facts}\n{considerations}\n"

    if input_data.scene_count_mode == "custom" and input_data.scene_count:
        scene_count_block = _scene_count_requirement(input_data.scene_count)
    else:
        scene_count_block = f"\n{SCENE_COUNT_DEFAULT_NOTE}\n"

    return f"""{SYSTEM_INSTRUCTION}
{scene_count_block}
Story idea: {input_data.story_idea}
Target total duration: {input_data.target_duration_seconds} seconds
{tone_line}{audience_line}{research_line}{correction_note}
Return JSON with exactly this shape:
{{
  "title": string, "logline": string, "theme": string,
  "target_duration_seconds": integer, "tone": string,
  "characters": [{{"name": string, "role": string, "one_line_description": string}}],
  "scenes": [{{"scene_id": integer, "title": string, "summary": string, "setting": string,
              "mood": string, "characters_present": [string], "estimated_duration_seconds": integer}}]
}}
"""
