import argparse
import json

from producer_studio.controller import ProducerStudioController
from project_manager.manager import ProjectManager


def main():
    parser = argparse.ArgumentParser(description="AI Video Studio - Producer Studio")
    parser.add_argument("--project-id", required=True, help="Project id created by a completed Director Studio run")
    args = parser.parse_args()

    project_manager = ProjectManager()
    controller = ProducerStudioController(project_manager)
    (
        _project, manifest, timeline, subtitle_plan, music_plan, editing_plan, thumbnail_plan, publishing_plan
    ) = controller.run(project_id=args.project_id)

    report = {"asset_validation": json.loads(manifest.model_dump_json())}
    if timeline is not None:
        report["timeline"] = json.loads(timeline.model_dump_json())
    if subtitle_plan is not None:
        report["subtitles"] = json.loads(subtitle_plan.model_dump_json())
    if music_plan is not None:
        report["music"] = json.loads(music_plan.model_dump_json())
    if editing_plan is not None:
        report["editing"] = json.loads(editing_plan.model_dump_json())
    if thumbnail_plan is not None:
        report["thumbnail"] = json.loads(thumbnail_plan.model_dump_json())
    if publishing_plan is not None:
        report["publishing"] = json.loads(publishing_plan.model_dump_json())

    print(json.dumps(report, indent=2))
    raise SystemExit(0 if manifest.is_valid else 1)


if __name__ == "__main__":
    main()
