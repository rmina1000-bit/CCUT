from .output_models import OutputSegment, EngineOutput


def build_minimal_output() -> EngineOutput:
    """
    Projection 기반 최소 결과 생성.
    Replay 이후에도 동일해야 한다.
    """
    from projection.projection_store import get_projection
    from decision_log import read_all_events

    events = read_all_events()

    cuts = {}
    for event in events:
        if event["type"] == "CREATE_CUT":
            p = event["payload"]
            cuts[p["id"]] = {"start": float(p["start"]), "end": float(p["end"])}
        elif event["type"] == "REMOVE_CUT":
            cuts.pop(event["payload"]["id"], None)

    projection = get_projection()

    segments = tuple(
        OutputSegment(
            segment_id=cut_id,
            start=data["start"],
            end=data["end"],
            label=cut_id
        )
        for cut_id, data in cuts.items()
    )

    return EngineOutput(
        version=projection.last_seq,
        segments=segments
    )
