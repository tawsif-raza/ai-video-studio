from agents.camera_planner.contract import CameraPlannerInput

SYSTEM_INSTRUCTION = """You are the Camera Planner agent inside an autonomous AI video studio.
You receive a confirmed shot list (the Shot Plan) and assign camera treatment - angle and
movement - to every shot. You do not touch narrative content, characters, or duration; that
is Shot Planner's responsibility and has already been settled.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Every scene_id and shot_id from the Shot Plan must appear exactly once in your output.
- Do not include shot description, characters, or duration - camera fields only.
- Vary camera language purposefully across shots; don't default to the same angle and
  movement for every shot in the plan.
"""


def build_camera_planner_prompt(input_data: CameraPlannerInput) -> str:
    shot_plan = input_data.shot_plan
    scenes_block = "\n\n".join(
        f"Scene {scene_plan.scene_id}:\n"
        + "\n".join(
            f"  Shot {shot.shot_id}: {shot.description} (duration: {shot.duration_seconds}s)"
            for shot in scene_plan.shots
        )
        for scene_plan in shot_plan.scene_plans
    )
    return f"""{SYSTEM_INSTRUCTION}

Shot Plan to assign camera treatment to:
{scenes_block}

Return JSON with exactly this shape:
{{
  "scene_plans": [
    {{
      "scene_id": integer,
      "shots": [
        {{
          "shot_id": integer,
          "camera_angle": string,
          "camera_movement": string
        }}
      ]
    }}
  ]
}}
"""
