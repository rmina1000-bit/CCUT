class EventValidationError(Exception):
    pass


EVENT_REGISTRY = {
    "CREATE_CUT": {
        "required_fields": {"id", "start", "end"},
    },
    "REMOVE_CUT": {
        "required_fields": {"id"},
    },
    "STATUS_CHANGE": {
        "required_fields": {"status"},
    },
    "META_UPDATE": {
        "required_fields": set(),
    },
}


def validate_event(event_type: str, payload: dict):
    if event_type not in EVENT_REGISTRY:
        raise EventValidationError(f"Unknown event type: {event_type}")

    required = EVENT_REGISTRY[event_type]["required_fields"]

    if not isinstance(payload, dict):
        raise EventValidationError("Payload must be a dict")

    missing = required - payload.keys()
    if missing:
        raise EventValidationError(
            f"Missing required fields: {missing}"
        )
