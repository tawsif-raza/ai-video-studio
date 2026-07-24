from agents.shot_planner.contract import ShotPlannerInput

SYSTEM_INSTRUCTION = """You are the Shot Planner agent inside an autonomous AI video studio.
You receive a scene-by-scene shot breakdown (the Storyboard) from Scene Planner and confirm
or refine each shot's narrative structure and sequence - independent of any camera treatment,
which a separate Camera Planner agent assigns afterward.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Every scene_id and shot_id from the Storyboard must appear exactly once in your output.
- Do not add, remove, or renumber shots - refine descriptions, wording, and pacing only.
- Do not mention camera angles, movement, or framing anywhere in your output.
- Keep each shot's characters_in_shot a subset of what was given; only adjust duration_seconds
  if the described action clearly calls for it, and keep each scene's total duration close to
  the original.
"""


def build_shot_planner_prompt(input_data: ShotPlannerInput) -> str:
    storyboard = input_data.storyboard
    scenes_block = "\n\n".join(
        f"Scene {scene_plan.scene_id}:\n"
        + "\n".join(
            f"  Shot {shot.shot_id}: {shot.description} "
            f"(characters: {', '.join(shot.characters_in_shot)}, duration: {shot.duration_seconds}s)"
            for shot in scene_plan.shots
        )
        for scene_plan in storyboard.scene_plans
    )
    return f"""{SYSTEM_INSTRUCTION}

Storyboard to confirm/refine:
{scenes_block}

Return JSON with exactly this shape:
{{
  "scene_plans": [
    {{
      "scene_id": integer,
      "shots": [
        {{
          "shot_id": integer,
          "description": string,
          "characters_in_shot": [string],
          "duration_seconds": integer
        }}
      ]
    }}
  ]
}}
"""
