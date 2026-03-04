from adapters.engine_read_adapter import read_projection


def build_projection_view() -> dict:
    return read_projection()
