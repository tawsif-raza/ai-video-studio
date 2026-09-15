# Backend image for AWS ECS (docs/aws-production-architecture.md §9: one
# image, two commands - infra/modules/ecs_api and ecs_worker both
# reference this same image, only the container `command` differs).
#
# Build context is the REPO ROOT, not ai_video_studio/ - this Dockerfile
# was previously written assuming the opposite (COPY requirements.txt .
# with no ai_video_studio/ prefix), which only worked under Railway's
# Nixpacks build (DEPLOYMENT.md: Root Directory = ai_video_studio,
# ffmpeg supplied by nixpacks.toml, this Dockerfile unused). Build with:
#   docker build -t <tag> -f Dockerfile .   (from the repo root)
FROM python:3.12-slim

# ffmpeg/ffprobe: execution_engine resolves both via shutil.which() on
# PATH (execution_engine/ffmpeg_detector.py, ffprobe_client.py) - no
# bundled binary, no absolute-path assumption. Previously supplied only by
# Railway's nixpacks.toml; this Dockerfile had no equivalent until now.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ai_video_studio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_video_studio/ .

EXPOSE 8000

# Default command runs the API (infra/modules/ecs_api/main.tf). The worker
# service (infra/modules/ecs_worker/main.tf) overrides this to
# ["python", "worker.py"] at the ECS task-definition level - same image,
# no rebuild needed to run the other role.
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "8000"]