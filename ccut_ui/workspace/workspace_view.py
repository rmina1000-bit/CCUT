from .fragment_mapper import map_projection_to_fragments


def build_workspace(projection: dict) -> dict:
    fragments = map_projection_to_fragments(projection)
    total_duration = round(max((f["end"] for f in fragments), default=0.0), 4)
    return {
        "fragments": fragments,
        "total_duration": total_duration,
        "fragment_count": len(fragments),
    }
