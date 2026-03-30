from __future__ import annotations

from mimetypes import guess_type

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

from app.services.publish_service import publish_service


router = APIRouter(tags=["published"])


@router.get("/published/{session_id}")
async def published_index(session_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/published/{session_id}/", status_code=307)


@router.get("/published/{session_id}/")
async def published_index_with_trailing_slash(session_id: str) -> FileResponse:
    target, is_fallback = publish_service.get_published_entry(session_id, "")
    media_type = "text/html" if is_fallback else guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)


@router.get("/published/{session_id}/{path:path}")
async def published_asset(session_id: str, path: str) -> FileResponse:
    target, is_fallback = publish_service.get_published_entry(session_id, path)
    media_type = "text/html" if is_fallback else guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)
