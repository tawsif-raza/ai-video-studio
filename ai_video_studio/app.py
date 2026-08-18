import argparse

from director_studio.controller import DirectorStudioController
from llm.failover_client import FailoverLLMClient as LLMClient
from llm.gemini_image_client import GeminiImageClient
from project_manager.manager import ProjectManager


def main():
    parser = argparse.ArgumentParser(description="AI Video Studio")
    parser.add_argument("--idea", required=True, help="Raw story idea / prompt")
    parser.add_argument("--duration", type=int, default=60, help="Target video duration in seconds")
    parser.add_argument("--tone", default=None)
    parser.add_argument("--audience", default=None)
    parser.add_argument("--art-style", default=None, help="e.g. '3D animated, Pixar-style, warm cinematic lighting'")
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Opt in to calling the image_generator agent (manual/preview tool, off by default - ARCHITECTURE.md SS2/SS15 Phase 6).",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="[Deprecated, no-op] Image generation is now opt-in by default; use --generate-images instead.",
    )
    parser.add_argument("--skip-research", action="store_true", help="Skip the Research stage and go straight to Story Planner")
    parser.add_argument(
        "--scene-count-mode",
        choices=["default", "custom"],
        default="default",
        help="'default' keeps the existing LLM-judged scene count; 'custom' requires --scene-count and makes it a hard requirement.",
    )
    parser.add_argument(
        "--scene-count",
        type=int,
        default=None,
        help="Exact number of scenes to generate. Required when --scene-count-mode=custom; ignored otherwise.",
    )
    args = parser.parse_args()

    if args.scene_count_mode == "custom" and args.scene_count is None:
        parser.error("--scene-count is required when --scene-count-mode=custom")

    llm = LLMClient()
    project_manager = ProjectManager()
    controller = DirectorStudioController(llm, project_manager)
    controller.run(
        idea=args.idea,
        duration=args.duration,
        tone=args.tone,
        audience=args.audience,
        art_style=args.art_style,
        skip_images=args.skip_images,
        generate_images=args.generate_images,
        skip_research=args.skip_research,
        scene_count_mode=args.scene_count_mode,
        scene_count=args.scene_count,
        image_client_factory=GeminiImageClient,
    )


if __name__ == "__main__":
    main()
