from fastapi import APIRouter

from web_api.models import HealthResponse, VersionResponse

# The web API layer's own version (web_api/, api_app.py) - independent of
# ARCHITECTURE.md's document revision number and of any future per-project
# data version. Bump this when the API's own surface changes shape.
API_VERSION = "0.1.0"

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    return VersionResponse(api_version=API_VERSION)
