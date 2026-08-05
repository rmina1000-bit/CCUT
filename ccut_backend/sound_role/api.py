"""SOUND-1 read and correction API."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .service import SoundRoleError, list_sound_roles, set_sound_role_override

router = APIRouter()


def _error(exc):
    return JSONResponse(
        status_code=exc.http_status,
        content={"ok": False, "error": exc.code, "message": exc.message, **exc.extra},
    )


@router.get("/sound-role/{program_id}")
async def get_sound_roles(program_id: str):
    try:
        return list_sound_roles(program_id)
    except SoundRoleError as exc:
        return _error(exc)

@router.post("/sound-role/{program_id}")
async def post_sound_role(program_id: str, payload: dict = None):
    body = payload or {}
    try:
        return set_sound_role_override(
            program_id,
            timeline_item_id=body.get("timeline_item_id"),
            fragment_id=body.get("fragment_id"),
            role=body.get("role"),
            expected_revision=body.get("expected_revision"),
        )
    except SoundRoleError as exc:
        return _error(exc)
