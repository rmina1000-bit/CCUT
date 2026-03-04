from .projection_state import ProjectionState

_projection = ProjectionState()


def apply_event_to_projection(event):
    _projection.apply(event)


def get_projection():
    return _projection


def rebuild_projection():
    from .projection_builder import build_projection
    global _projection
    _projection = build_projection()
