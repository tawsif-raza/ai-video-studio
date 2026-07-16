from pathlib import Path

from agents.base.exceptions import ContractViolationError

MIN_VALID_IMAGE_BYTES = 5_000

def validate_image_file(file_path: Path) -> Path:
    if not file_path.exists():
        raise ContractViolationError(f"Image file was not created: {file_path}")

    size = file_path.stat().st_size
    if size < MIN_VALID_IMAGE_BYTES:
        raise ContractViolationError(
            f"Image file at {file_path} is only {size} bytes - likely corrupt or truncated"
        )

    return file_path
