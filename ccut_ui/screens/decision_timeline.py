from adapters.engine_read_adapter import read_decision_log, read_trace, preview_replay


def build_decision_timeline(limit: int = 200) -> dict:
    return {
        "events": read_decision_log(limit),
        "trace": read_trace(50),
        "replay_preview": preview_replay(),
    }
