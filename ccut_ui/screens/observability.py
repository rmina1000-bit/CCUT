from adapters.engine_read_adapter import read_metrics, read_status


def build_observability_view() -> dict:
    return {
        "metrics": read_metrics(),
        "health": read_status(),
    }
