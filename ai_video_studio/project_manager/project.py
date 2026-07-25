import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProjectState(str, Enum):
    """
    Implements ARCHITECTURE.md SS8's full 14-state machine. SHOTS_COMPLETE and
    CAMERA_COMPLETE were added once the Shot Planner and Camera Planner agents
    landed (roadmap Phase 7), closing the gap tracked in the Active Technical
    Debt Ledger. RESEARCHED was added once the Research agent (roadmap Phase 8)
    landed. MEDIA_IMPORTED was added once Asset Validation landed (roadmap
    Phase 11, Milestone 1). EDIT_PLAN_READY was added once the last of the six
    planning sub-stages landed (Publishing Metadata, roadmap Phase 11,
    Milestone 7): it means Timeline, Subtitle, Music, Editing, Thumbnail, AND
    Publishing Metadata are ALL done, exactly as PROMPTS_COMPLETE requires both
    Prompt Intelligence and Voice Script. VIDEO_RENDERED was added once the
    FFmpeg Execution Engine's postflight validation landed (Milestone 8.4):
    reaching it requires BOTH a successful ffmpeg exit (RenderResult.success)
    AND a passing postflight quality verdict (RenderValidationReport.is_valid)
    - a process success alone is not sufficient. PUBLISHED is still not
    implemented, since the publishing executor doesn't exist yet.
    """

    CREATED = "CREATED"
    RESEARCHED = "RESEARCHED"
    STORY_COMPLETE = "STORY_COMPLETE"
    SCENES_COMPLETE = "SCENES_COMPLETE"
    SHOTS_COMPLETE = "SHOTS_COMPLETE"
    CAMERA_COMPLETE = "CAMERA_COMPLETE"
    CHARACTERS_COMPLETE = "CHARACTERS_COMPLETE"
    ENVIRONMENTS_COMPLETE = "ENVIRONMENTS_COMPLETE"
    PROMPTS_COMPLETE = "PROMPTS_COMPLETE"
    PACKAGE_READY = "PACKAGE_READY"
    MEDIA_IMPORTED = "MEDIA_IMPORTED"
    EDIT_PLAN_READY = "EDIT_PLAN_READY"
    VIDEO_RENDERED = "VIDEO_RENDERED"


class Project(BaseModel):
    """
    The unit of persistent work Project Manager owns end to end (ARCHITECTURE.md
    SS4/SS8). project_id is generated at create_project() time - before Story
    Planner ever runs - so it's available to key the package/project.json
    location from the very start, unlike plan.plan_id, which only exists once
    the first stage completes.
    """

    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ProjectState = ProjectState.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    source_research_brief_id: Optional[str] = None
    source_plan_id: Optional[str] = None
    source_storyboard_id: Optional[str] = None
    source_shot_plan_id: Optional[str] = None
    source_camera_plan_id: Optional[str] = None
    source_character_sheet_id: Optional[str] = None
    source_environment_sheet_id: Optional[str] = None
    source_prompt_set_id: Optional[str] = None
    source_voice_script_id: Optional[str] = None
    production_package_dir: Optional[str] = None
    image_manifest_path: Optional[str] = None
    source_asset_manifest_id: Optional[str] = None
    source_timeline_id: Optional[str] = None
    source_subtitle_plan_id: Optional[str] = None
    source_music_plan_id: Optional[str] = None
    source_editing_plan_id: Optional[str] = None
    source_thumbnail_plan_id: Optional[str] = None
    source_publishing_metadata_id: Optional[str] = None
    producer_package_dir: Optional[str] = None
    rendered_video_path: Optional[str] = None
