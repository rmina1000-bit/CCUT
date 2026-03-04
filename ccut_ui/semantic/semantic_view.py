from workspace.fragment_mapper import map_projection_to_fragments
from .semantic_analyzer import suggest_groups


def build_semantic_view(projection: dict) -> dict:
    fragments = map_projection_to_fragments(projection)
    suggestions = suggest_groups(fragments)
    return {
        "fragments": fragments,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
    }
