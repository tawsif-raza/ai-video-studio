from agents.story_planner.contract import StoryPlannerInput

SYSTEM_INSTRUCTION = """You are the Story Planner agent inside an autonomous AI video studio.
Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
Break the story into short scenes (2-15s each) suitable for short-form vertical video.
Total scene duration must be close to the target duration (within ~30%).
Every name in a scene's characters_present must also appear in the top-level characters list.
"""


def build_story_planner_prompt(input_data: StoryPlannerInput) -> str:
    tone_line = f"Desired tone: {input_data.tone}\n" if input_data.tone else ""
    audience_line = f"Target audience: {input_data.audience}\n" if input_data.audience else ""
    research_line = ""
    if input_data.research_key_facts or input_data.research_considerations:
        facts = "\n".join(f"- {f}" for f in input_data.research_key_facts)
        considerations = "\n".join(f"- {c}" for c in input_data.research_considerations)
        research_line = f"\nBackground research:\n{facts}\n{considerations}\n"
    return f"""{SYSTEM_INSTRUCTION}

Story idea: {input_data.story_idea}
Target total duration: {input_data.target_duration_seconds} seconds
{tone_line}{audience_line}{research_line}
Return JSON with exactly this shape:
{{
  "title": string, "logline": string, "theme": string,
  "target_duration_seconds": integer, "tone": string,
  "characters": [{{"name": string, "role": string, "one_line_description": string}}],
  "scenes": [{{"scene_id": integer, "title": string, "summary": string, "setting": string,
              "mood": string, "characters_present": [string], "estimated_duration_seconds": integer}}]
}}
"""