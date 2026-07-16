from agents.character_planner.contract import CharacterPlannerInput

SYSTEM_INSTRUCTION = """You are the Character Planner agent inside an autonomous AI video studio.
You receive a finished Production Plan and produce a detailed visual reference sheet for
every character, so their appearance stays consistent across every image and video shot
generated later in the pipeline.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Every character in the Production Plan's characters list must get exactly one profile —
  do not skip characters, do not invent new ones.
- All characters must share a consistent overall art style (matching the provided
  art_style if given) so they look like they belong in the same film.
- reference_prompt must be a single, self-contained paragraph specific enough that an
  image model could render this exact character from it alone, with no other context.
- Keep color_palette to the character's actual dominant colors, not a generic palette.
"""


def build_character_planner_prompt(input_data: CharacterPlannerInput) -> str:
    plan = input_data.production_plan
    style_line = (
        f"Required art style for all characters: {input_data.art_style}\n"
        if input_data.art_style
        else "No specific art style was given — infer one that fits the story's tone and theme.\n"
    )

    characters_block = "\n".join(
        f'- {c.name} ({c.role}): {c.one_line_description}' for c in plan.characters
    )

    return f"""{SYSTEM_INSTRUCTION}

Story: {plan.title} — {plan.logline}
Theme: {plan.theme}
Overall tone: {plan.tone}
{style_line}
Characters to profile:
{characters_block}

Return JSON with exactly this shape:
{{
  "character_profiles": [
    {{
      "name": string,
      "age_range": string,
      "build": string,
      "face_details": string,
      "hair": string,
      "outfit": string,
      "color_palette": [string],
      "distinguishing_features": string,
      "art_style_keywords": [string],
      "reference_prompt": string
    }}
  ]
}}
"""