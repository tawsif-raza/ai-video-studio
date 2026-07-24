import argparse

from director_studio.controller import DirectorStudioController
from llm.groq_client import GroqClient as LLMClient
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
    args = parser.parse_args()

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
        image_client_factory=GeminiImageClient,
    )


if __name__ == "__main__":
    main()
