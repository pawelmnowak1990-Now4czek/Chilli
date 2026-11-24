"""Saving uploaded images to the server disk.

In step 2 we keep the original in the `incoming/` subdirectory. Step 4 (processing) will make a
permanent smaller copy of it and delete the original, as decided in CLAUDE.md.
"""

from pathlib import Path
from uuid import UUID

from app.config import settings

# Image types the iPhone sends (a screenshot is usually PNG, photos can be HEIC),
# and the file extension for each of them.
IMAGE_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/webp": ".webp",
}


def detect_image_type(declared_type: str | None, data: bytes) -> str | None:
    """Determines the image type or returns None when it is not a supported image.

    First we trust the type given by the client. When the client sent the generic
    "application/octet-stream" (it happens in Shortcuts), we recognize PNG and JPEG
    by the first bytes of the file, the so-called signature.
    """
    if declared_type in IMAGE_EXTENSIONS:
        return declared_type
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def save_incoming_image(save_id: UUID, content_type: str, data: bytes) -> Path:
    """Saves the image as `<images_dir>/incoming/<save id>.<extension>` and returns the path.

    The file name is the row id from the database, so a user-supplied name never reaches the disk
    (no "../" or strange characters).
    """
    folder = Path(settings.images_dir) / "incoming"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{save_id}{IMAGE_EXTENSIONS[content_type]}"
    path.write_bytes(data)
    return path
