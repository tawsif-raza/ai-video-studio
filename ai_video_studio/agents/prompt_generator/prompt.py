from agents.prompt_generator.contract import PromptGeneratorInput

SYSTEM_INSTRUCTION = """You are the Prompt Generator agent inside an autonomous AI video studio.
You receive everything needed to describe ONE shot - the shot's action, camera framing,
the visual reference for every character in it, and the visual reference for its setting.
Your job is to fuse all of that into a single polished image-generation prompt, plus a
short motion prompt for video generation.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- image_prompt must be one self-contained paragraph combining: the character
  appearance(s), the environment, the shot's specific action, and the camera framing
  (angle + movement). An image model must be able to render this from image_prompt
  alone, with no other context.
- Do not just concatenate the reference prompts - weave them into one coherent scene
  description, keeping every specific visual detail (colors, features, outfit) intact.
- video_motion_prompt is short (1-2 sentences): describe only what moves and how the
  camera moves during this shot's duration. It must NOT just repeat image_prompt.
- Preserve the required art style in both outputs if one was given.
"""


def build_prompt_generator_prompt(input_data: PromptGeneratorInput) -> str:
    characters_block = "\n\n".join(
        f"Character - {c.name}: {c.reference_prompt}" for c in input_data.character_profiles
    )
    style_line = f"Required art style: {input_data.art_style}\n" if input_data.art_style else ""

    return f"""{SYSTEM_INSTRUCTION}

{characters_block}

Environment - {input_data.environment_profile.setting}: {input_data.environment_profile.reference_prompt}

Shot to describe:
- What happens: {input_data.shot_description}
- Camera angle: {input_data.camera_angle}
- Camera movement: {input_data.camera_movement}
- Duration: {input_data.duration_seconds}s
{style_line}
Return JSON with exactly this shape:
{{
  "image_prompt": string,
  "video_motion_prompt": string
}}
"""
