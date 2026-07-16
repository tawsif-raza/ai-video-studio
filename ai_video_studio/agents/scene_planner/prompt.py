from agents.scene_planner.contract import ScenePlannerInput

SYSTEM_INSTRUCTION = """You are the Scene Planner agent inside an autonomous AI video studio.
You receive a finished Production Plan and turn every scene into a camera storyboard.

Rules:
- Output ONLY valid JSON matching the schema below. No prose, no markdown fences.
- Every scene_id from the Production Plan must appear exactly once in your output.
- Shot durations within a scene must add up to approximately that scene's target duration.
- Only reference characters already listed as present in that specific scene.
- Vary camera language purposefully; don't default to the same angle for every shot.
"""


def build_scene_planner_prompt(input_data: ScenePlannerInput) -> str:
    plan = input_data.production_plan
    scenes_block = "\n".join(
        f'''Scene {s.scene_id}: "{s.title}"
- Summary: {s.summary}
- Setting: {s.setting}
- Mood: {s.mood}
- Characters present: {', '.join(s.characters_present)}
- Target duration: {s.estimated_duration_seconds}s'''
        for s in plan.scenes
    )
    return f'''{SYSTEM_INSTRUCTION}

Story: {plan.title} — {plan.logline}
Overall tone: {plan.tone}

Scenes to storyboard:
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
          "camera_movement": string,
          "description": string,
          "characters_in_shot": [string],
          "duration_seconds": integer
        }}
      ]
    }}
  ]
}}
'''
