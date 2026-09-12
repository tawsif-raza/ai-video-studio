from fastapi import APIRouter
from pydantic import BaseModel

from config import settings

router = APIRouter(prefix="/health", tags=["health"])

class HealthStatus(BaseModel):
    status: str

@router.get("/live", response_model=HealthStatus)
def liveness():
    """Liveness probe: returns 200 if the process is up and running."""
    return HealthStatus(status="ok")

@router.get("/ready", response_model=HealthStatus)
def readiness():
    """Readiness probe: checks if essential dependencies are available."""
    # The application is mostly file-system backed, so check if OUTPUT_DIR is accessible
    try:
        if not settings.OUTPUT_DIR.exists():
            settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # Test basic write access
        test_file = settings.OUTPUT_DIR / ".health_test"
        test_file.write_text("ok")
        test_file.unlink()
        return HealthStatus(status="ready")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=f"Dependencies not ready: {str(e)}")
