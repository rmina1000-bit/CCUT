from types import MappingProxyType
from hash_util import compute_event_hash


class VerificationError(Exception):
    pass


def verify_log(events):
    """
    전체 로그 무결성 검사
    return: {
        "valid": bool,
        "event_count": int,
        "last_hash": str
    }
    """

    expected_seq = 0
    previous_hash = "NONE"

    for event in events:

        if not isinstance(event, MappingProxyType):
            raise VerificationError("Non-immutable event detected")

        if set(event.keys()) != {"seq", "type", "payload", "prev_hash", "hash"}:
            raise VerificationError("Event structure corrupted")

        if event["seq"] != expected_seq:
            raise VerificationError("Sequence violation")

        if event["seq"] == 0:
            if event["type"] != "GENESIS":
                raise VerificationError("Missing GENESIS block")

        if event["prev_hash"] != previous_hash:
            raise VerificationError("Hash chain broken")

        recalculated = compute_event_hash(
            event["seq"],
            event["type"],
            dict(event["payload"]),
            event["prev_hash"]
        )

        if recalculated != event["hash"]:
            raise VerificationError("Hash mismatch")

        previous_hash = event["hash"]
        expected_seq += 1

    return {
        "valid": True,
        "event_count": len(events),
        "last_hash": previous_hash
    }


def verify_projection():
    from projection.projection_builder import build_projection

    state = build_projection()

    assert state.last_seq >= 0
    assert state.status in ["INIT", "READY", "RUNNING", "STOPPED"]

    return True


def verify_view_layer():
    from projection.view_builder import build_engine_view

    view = build_engine_view()

    assert isinstance(view.status, str)
    assert isinstance(view.last_seq, int)
    assert isinstance(view.meta, dict)

    return True


def verify_incremental_projection():
    from projection.projection_store import get_projection
    p = get_projection()

    assert p.last_seq >= 0

    return True


def verify_output_stability():
    from output.output_builder import build_minimal_output

    out1 = build_minimal_output()
    out2 = build_minimal_output()

    assert out1 == out2, "Output is not deterministic"

    return True


def verify_artifact_stability():
    from output.artifact_writer import build_output_artifact

    p1 = build_output_artifact()
    b1 = p1.read_bytes()

    p2 = build_output_artifact()
    b2 = p2.read_bytes()

    assert b1 == b2, "Artifact not deterministic"

    return True


def verify_render_request_stability():
    from render.render_planner import build_render_request

    r1 = build_render_request()
    r2 = build_render_request()

    assert r1 == r2, "RenderRequest not deterministic"

    return True


def verify_render_execution():
    from render.render_planner import build_render_request
    from render.render_executor import execute_render

    req = build_render_request()

    p1 = execute_render(req)
    b1 = p1.read_bytes()

    p2 = execute_render(req)
    b2 = p2.read_bytes()

    assert b1 == b2, "Render execution not deterministic"

    return True


def verify_worker_isolation():
    from render.render_planner import build_render_request
    from render.queue import enqueue_render, QUEUE_DIR
    from render.worker import process_queue_once
    from render.render_executor import RENDER_DIR

    req = build_render_request()

    queue_path = enqueue_render(req)
    assert queue_path.exists(), "Queue file not created"

    process_queue_once()

    render_path = RENDER_DIR / f"render_v{req.version}.json"
    assert render_path.exists(), "Render file not created by worker"
    assert not queue_path.exists(), "Queue file not removed after processing"

    return True
