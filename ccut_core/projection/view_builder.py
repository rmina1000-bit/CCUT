from .projection_store import get_projection
from .view_dto import EngineView


def build_engine_view() -> EngineView:
    p = get_projection()

    return EngineView(
        status=p.status,
        last_seq=p.last_seq,
        meta=dict(p.meta)
    )
