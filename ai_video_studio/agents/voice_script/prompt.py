from agents.voice_script.contract import VoiceScriptInput

SYSTEM_INSTRUCTION = """You are the Voice Script agent inside an autonomous AI video studio.
You receive a finished Production Plan and Storyboard and write the full narration/dialogue
script that will be read aloud over the finished video.

Rules:
- Output ONLY valid JSON matching the schema below. No prose or markdown fences.
- Write exactly one narration passage per scene, covering every scene in the Production Plan.
- Narration should accompany the on-screen action described in that scene's shots, without
  literally describing camera direction (angles, movement) - that belongs to the visuals,
  not the voice.
- Match the story's tone and theme throughout.
- Keep pacing plausible for the scene's estimated duration - a few sentences for a short
  scene, not a monologue.
"""


def build_voice_script_prompt(input_data: VoiceScriptInput) -> str:
    plan = input_data.production_plan
    shots_by_scene = {
        scene_plan.scene_id: scene_plan.shots for scene_plan in input_data.storyboard.scene_plans
    }

    scene_blocks = []
    for scene in plan.scenes:
        shots = shots_by_scene.get(scene.scene_id, [])
        shots_lines = "\n".join(f"    - {shot.description}" for shot in shots)
        scene_blocks.append(
            f"Scene {scene.scene_id}: {scene.title} ({scene.estimated_duration_seconds}s)\n"
            f"  Setting: {scene.setting} | Mood: {scene.mood}\n"
            f"  Summary: {scene.summary}\n"
            f"  Shots:\n{shots_lines}"
        )
    scenes_block = "\n\n".join(scene_blocks)

    return f"""{SYSTEM_INSTRUCTION}

Story: {plan.title} — {plan.logline}
Theme: {plan.theme}
Overall tone: {plan.tone}

Scenes:
{scenes_block}

Return JSON with exactly this shape:
{{
  "lines": [
    {{
      "scene_id": integer,
      "narration_text": string
    }}
  ]
}}
"""
