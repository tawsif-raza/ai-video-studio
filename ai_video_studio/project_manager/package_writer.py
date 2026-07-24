# Package writer, owned by Project Manager (ARCHITECTURE.md SS4/SS7): the
# Production Package's shape is defined once, as typed schemas in
# shared_core/contracts (SS7, SS15 Phase 5); this module only serializes
# instances of those types to disk.

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from shared_core.contracts.camera_plan import CameraPlan
from shared_core.contracts.character_sheet import CharacterSheet
from shared_core.contracts.environment_sheet import EnvironmentSheet
from shared_core.contracts.production_plan import ProductionPlan
from shared_core.contracts.prompt_set import PromptSet
from shared_core.contracts.research import ResearchBrief
from shared_core.contracts.shot_plan import ShotPlan
from shared_core.contracts.storyboard import Storyboard
from shared_core.contracts.voice_script import VoiceScript
from config import settings

VOICE_SCRIPT_STUB = (
    "# Voice script pending\n"
    "#\n"
    "# The Voice Script agent has not been implemented yet\n"
    "# (see ARCHITECTURE.md SS15, Phase 9).\n"
    "# This file is a placeholder so the Production Package\n"
    "# structure is stable ahead of that agent's introduction.\n"
)

RESEARCH_BRIEF_SKIPPED_STUB = {
    "status": "skipped",
    "reason": "Research stage was skipped via --skip-research for this run.",
}

MANIFEST_DESCRIPTIONS = {
    "metadata.json": "Package-level metadata: project id, generation timestamps, target duration, art style.",
    "research_brief.json": "Supporting context and considerations gathered before story planning.",
    "story.md": "Human-readable story: title, logline, theme, tone, character list, scene list.",
    "scene_plan.json": "Scene-level breakdown: setting, mood, characters present, estimated duration.",
    "shot_plan.json": "Per-scene shot list: what happens in each shot, characters in shot, duration.",
    "camera_plan.json": "Per-shot camera angle and movement.",
    "character_bible.json": "One visual profile per character.",
    "environment_bible.json": "One visual profile per unique setting.",
    "image_prompts.json": "Final, polished image-generation prompt per shot.",
    "video_prompts.json": "Final motion/camera prompt per shot.",
    "voice_script.txt": "Full narration/dialogue script in reading order.",
}


def _build_story_markdown(plan: ProductionPlan) -> str:
    lines = [
        f"# {plan.title}",
        "",
        f"**Logline:** {plan.logline}",
        "",
        f"**Theme:** {plan.theme}  ",
        f"**Tone:** {plan.tone}  ",
        f"**Target Duration:** {plan.target_duration_seconds}s",
        "",
        "## Characters",
        "",
    ]
    for character in plan.characters:
        lines.append(f"- **{character.name}** ({character.role}): {character.one_line_description}")
    lines += ["", "## Scenes", ""]
    for scene in plan.scenes:
        lines += [
            f"### Scene {scene.scene_id}: {scene.title}",
            f"- **Setting:** {scene.setting}",
            f"- **Mood:** {scene.mood}",
            f"- **Characters:** {', '.join(scene.characters_present)}",
            f"- **Duration:** {scene.estimated_duration_seconds}s",
            "",
            scene.summary,
            "",
        ]
    return "\n".join(lines)


def _build_scene_plan(plan: ProductionPlan) -> List[dict]:
    return [
        {
            "scene_id": scene.scene_id,
            "title": scene.title,
            "summary": scene.summary,
            "setting": scene.setting,
            "mood": scene.mood,
            "characters_present": scene.characters_present,
            "estimated_duration_seconds": scene.estimated_duration_seconds,
        }
        for scene in plan.scenes
    ]


def _build_shot_plan(shot_plan: ShotPlan) -> List[dict]:
    return [
        {
            "scene_id": scene_plan.scene_id,
            "shots": [
                {
                    "shot_id": shot.shot_id,
                    "description": shot.description,
                    "characters_in_shot": shot.characters_in_shot,
                    "duration_seconds": shot.duration_seconds,
                }
                for shot in scene_plan.shots
            ],
        }
        for scene_plan in shot_plan.scene_plans
    ]


def _build_camera_plan(camera_plan: CameraPlan) -> List[dict]:
    return [
        {
            "scene_id": scene_plan.scene_id,
            "shots": [
                {
                    "shot_id": shot.shot_id,
                    "camera_angle": shot.camera_angle,
                    "camera_movement": shot.camera_movement,
                }
                for shot in scene_plan.shots
            ],
        }
        for scene_plan in camera_plan.scene_plans
    ]


def _build_image_prompts(prompt_set: PromptSet) -> List[dict]:
    return [
        {"scene_id": shot.scene_id, "shot_id": shot.shot_id, "image_prompt": shot.image_prompt}
        for shot in prompt_set.shots
    ]


def _build_video_prompts(prompt_set: PromptSet) -> List[dict]:
    return [
        {"scene_id": shot.scene_id, "shot_id": shot.shot_id, "video_motion_prompt": shot.video_motion_prompt}
        for shot in prompt_set.shots
    ]


def _build_voice_script_text(voice_script: VoiceScript) -> str:
    ordered_lines = sorted(voice_script.lines, key=lambda line: line.scene_id)
    return "\n\n".join(line.narration_text for line in ordered_lines)


def _build_metadata(
    project_id: str,
    plan: ProductionPlan,
    storyboard: Storyboard,
    tone: Optional[str],
    audience: Optional[str],
    art_style: Optional[str],
) -> dict:
    return {
        "package_id": project_id,
        "source_plan_id": plan.plan_id,
        "source_storyboard_id": storyboard.storyboard_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "target_duration_seconds": plan.target_duration_seconds,
        "tone": tone,
        "audience": audience,
        "art_style": art_style,
    }


def _build_manifest(package_id: str, voice_script_status: str, research_brief_status: str) -> dict:
    files = []
    status_overrides = {
        "voice_script.txt": voice_script_status,
        "research_brief.json": research_brief_status,
    }
    for name, description in MANIFEST_DESCRIPTIONS.items():
        status = status_overrides.get(name, "generated")
        files.append({"name": name, "description": description, "status": status})
    return {
        "package_id": package_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": files,
    }


def write_production_package(
    *,
    project_id: str,
    plan: ProductionPlan,
    storyboard: Storyboard,
    shot_plan: ShotPlan,
    camera_plan: CameraPlan,
    character_sheet: CharacterSheet,
    environment_sheet: EnvironmentSheet,
    prompt_set: PromptSet,
    research_brief: Optional[ResearchBrief] = None,
    voice_script: Optional[VoiceScript] = None,
    tone: Optional[str] = None,
    audience: Optional[str] = None,
    art_style: Optional[str] = None,
) -> Path:
    """Writes projects/<project_id>/production-package/ as a second, additive
    output alongside the legacy flat outputs/*.json files. Never reads or
    modifies any legacy output."""
    package_dir = settings.OUTPUT_DIR / "projects" / project_id / "production-package"
    package_dir.mkdir(parents=True, exist_ok=True)

    (package_dir / "metadata.json").write_text(
        json.dumps(_build_metadata(project_id, plan, storyboard, tone, audience, art_style), indent=2)
    )

    if research_brief is not None:
        (package_dir / "research_brief.json").write_text(research_brief.model_dump_json(indent=2))
        research_brief_status = "generated"
    else:
        (package_dir / "research_brief.json").write_text(json.dumps(RESEARCH_BRIEF_SKIPPED_STUB, indent=2))
        research_brief_status = "skipped"

    (package_dir / "story.md").write_text(_build_story_markdown(plan))
    (package_dir / "scene_plan.json").write_text(json.dumps(_build_scene_plan(plan), indent=2))
    (package_dir / "shot_plan.json").write_text(json.dumps(_build_shot_plan(shot_plan), indent=2))
    (package_dir / "camera_plan.json").write_text(json.dumps(_build_camera_plan(camera_plan), indent=2))
    (package_dir / "character_bible.json").write_text(character_sheet.model_dump_json(indent=2))
    (package_dir / "environment_bible.json").write_text(environment_sheet.model_dump_json(indent=2))
    (package_dir / "image_prompts.json").write_text(json.dumps(_build_image_prompts(prompt_set), indent=2))
    (package_dir / "video_prompts.json").write_text(json.dumps(_build_video_prompts(prompt_set), indent=2))

    if voice_script is not None:
        (package_dir / "voice_script.txt").write_text(_build_voice_script_text(voice_script))
        voice_script_status = "generated"
    else:
        (package_dir / "voice_script.txt").write_text(VOICE_SCRIPT_STUB)
        voice_script_status = "pending"

    manifest = _build_manifest(
        project_id, voice_script_status=voice_script_status, research_brief_status=research_brief_status
    )
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return package_dir
