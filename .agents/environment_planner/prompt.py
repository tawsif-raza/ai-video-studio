from agents.environment_planner.contract import EnvironmentPlannerInput, get_unique_settings

SYSTEM_INSTRUCTION = """You are the Environment Planner agent inside an autonomous AI video studio.
You receive a finished Production Plan and produce a detailed visual reference for every
unique location, so backgrounds stay consistent across every shot set in that location.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- You will be given an exact list of unique setting strings. Produce exactly one profile
  per setting, and copy the setting string into the "setting" field character-for-character
  — do not paraphrase or reword it.
- Match the art style used for characters so backgrounds and characters belong in the
  same film (matching the provided art_style if given).
- reference_prompt must be a single, self-contained paragraph specific enough that an
  image model could render this exact location from it alone, with no other context.
"""


def build_environment_planner_prompt(input_data: EnvironmentPlannerInput) -> str:
    plan = input_data.production_plan
    unique_settings = get_unique_settings(plan)

    style_line = (
        f"Required art style (must match characters): {input_data.art_style}\n"
        if input_data.art_style
        else "No specific art style was given — infer one that fits the story's tone and theme.\n"
    )

    settings_block = "\n".join(f'- "{s}"' for s in unique_settings)

    return f"""{SYSTEM_INSTRUCTION}

Story: {plan.title} — {plan.logline}
Theme: {plan.theme}
Overall tone: {plan.tone}
{style_line}
Unique settings to profile (exactly one profile per line, copied verbatim into "setting"):
{settings_block}

Return JSON with exactly this shape:
{{
  "environment_profiles": [
    {{
      "setting": string,
      "time_of_day": string,
      "weather": string,
      "key_visual_elements": [string],
      "color_palette": [string],
      "lighting": string,
      "atmosphere": string,
      "art_style_keywords": [string],
      "reference_prompt": string
    }}
  ]
}}
"""