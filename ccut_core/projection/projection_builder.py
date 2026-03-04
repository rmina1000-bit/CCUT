from .projection_state import ProjectionState


def build_projection() -> ProjectionState:
    from decision_log import read_all_events

    state = ProjectionState()
    events = read_all_events()

    for event in events:
        state.apply(event)

    return state
