"""POST /capture: accepts a screenshot or a link and answers right away.

Three request shapes under one address (phone shortcuts: shortcuts/README.md, Chrome extension: extension/):
- multipart form with an `image` field (image file)  -> source_type = 'screenshot'
- JSON `{"url": "https://..."}`                      -> source_type = 'link'
- JSON `{"text": "...", "url": ..., "title": ...}`   -> source_type = 'text' (selected fragment of a page)

Nothing is analysed here. The row goes to the database with processed_at = NULL, the response
is sent immediately, and the save is processed in the background by app/processing.py (steps 4 and 5).
"""

import json
import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator
from starlette.datastructures import UploadFile

from app import db, processing, saves, storage
from app.auth import require_capture_token
from app.config import settings

router = APIRouter()


# First http(s) address in a text: everything from "http" up to the nearest whitespace.
URL_IN_TEXT = re.compile(r"https?://\S+")


class CaptureLink(BaseModel):
    """JSON body for a link. HttpUrl rejects everything that is not an http(s) address."""

    url: HttpUrl

    @field_validator("url", mode="before")
    @classmethod
    def extract_url(cls, value: object) -> object:
        """Some apps (e.g. X) share a link as text with extra words around it.
        We pull the first address out of it before HttpUrl checks it (mode="before")."""
        if isinstance(value, str):
            match = URL_IN_TEXT.search(value)
            if match:
                return match.group(0)
        return value


class CaptureText(BaseModel):
    """Text selected in the browser. The page address and title are extras: a bad address
    (e.g. chrome://newtab) is skipped so it does not block saving the text."""

    text: str = Field(min_length=1, max_length=200_000)
    url: str | None = None
    title: str | None = Field(default=None, max_length=500)

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty text")
        return value


class CaptureAccepted(BaseModel):
    """Response: the id of the new save. The Shortcut only shows "Saved in Chilli"."""

    id: UUID
    status: str = "accepted"


@router.post(
    "/capture",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_capture_token)],
)
async def capture(request: Request, background: BackgroundTasks) -> CaptureAccepted:
    # 202 Accepted = "accepted, I will process it later". The content type decides which path we take.
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        accepted = await _capture_image(request)
        # BackgroundTasks: FastAPI runs this function only after the response has been sent to the phone.
        background.add_task(processing.process_save, accepted.id)
        return accepted
    if content_type.startswith("application/json"):
        body = await request.body()
        # A `text` field = selection from the browser; without it this is a link (Shortcut, extension button).
        if _has_text_field(body):
            accepted = _capture_text(body)
        else:
            accepted = _capture_link(body)
        background.add_task(processing.process_save, accepted.id)
        return accepted
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send a form with an image field or JSON with a url field"
    )


def _has_text_field(body: bytes) -> bool:
    try:
        data = json.loads(body)
    except ValueError:
        return False  # broken JSON is handled by the link validation (422)
    return isinstance(data, dict) and "text" in data


def _capture_text(body: bytes) -> CaptureAccepted:
    try:
        captured = CaptureText.model_validate_json(body)
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from error

    save_id = uuid4()
    with db.connect() as conn:
        saves.insert_capture(
            conn, save_id, source_type="text", url=_optional_url(captured.url),
            content_text=captured.text, title=captured.title,
        )
    return CaptureAccepted(id=save_id)


def _capture_link(body: bytes) -> CaptureAccepted:
    try:
        link = CaptureLink.model_validate_json(body)
    except ValidationError as error:
        # The same 422 error format that FastAPI returns for ordinary models.
        raise RequestValidationError(error.errors()) from error

    save_id = uuid4()
    with db.connect() as conn:
        saves.insert_capture(conn, save_id, source_type="link", url=str(link.url))
    return CaptureAccepted(id=save_id)


async def _capture_image(request: Request) -> CaptureAccepted:
    form = await request.form()
    upload = form.get("image")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no file in the image field")

    # We read one byte more than the limit: if that worked, the file is too large.
    limit = settings.max_upload_mb * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"image larger than {settings.max_upload_mb} MB"
        )

    image_type = storage.detect_image_type(upload.content_type, data)
    if image_type is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "this is not a supported image")

    page_url = _optional_url(form.get("url"))

    save_id = uuid4()
    path = storage.save_incoming_image(save_id, image_type, data)
    try:
        with db.connect() as conn:
            saves.insert_capture(
                conn, save_id, source_type="screenshot", image_path=str(path), url=page_url
            )
    except Exception:
        # Without a row in the database the file would be an orphan that nobody cleans up.
        Path(path).unlink(missing_ok=True)
        raise
    return CaptureAccepted(id=save_id)


def _optional_url(value: object) -> str | None:
    """Page address attached to a screenshot (the `url` form field) or None.

    The Shortcut sends here whatever iOS gave as the "screen content"; sometimes it is an
    address, sometimes plain text. An invalid value must not block saving the screenshot,
    so we skip it.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(CaptureLink(url=value).url)
    except ValidationError:
        return None
