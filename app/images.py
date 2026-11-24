"""Shrinking screenshots to the copy we keep permanently.

Decision from CLAUDE.md: we delete the original after processing, a smaller, compressed copy stays.
WebP at quality 80 is usually 5-10 times smaller than a PNG from the iPhone, and the text is still readable.
"""

from pathlib import Path

from PIL import Image

from app.config import settings


def shrink_to_webp(source: Path, target: Path) -> Path:
    """Saves `source` as WebP in `target`, with the longer side at most `image_max_side`.

    `thumbnail` shrinks the image keeping proportions and never enlarges it.
    """
    with Image.open(source) as image:
        image = image.convert("RGB")  # WebP does not accept every color mode from PNG (e.g. palette)
        image.thumbnail((settings.image_max_side, settings.image_max_side))
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, format="WEBP", quality=80)
    return target
