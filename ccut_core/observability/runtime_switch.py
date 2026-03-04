OBSERVABILITY_ENABLED: bool = True


def is_enabled() -> bool:
    return OBSERVABILITY_ENABLED


def enable():
    global OBSERVABILITY_ENABLED
    OBSERVABILITY_ENABLED = True
    try:
        from .audit_log import record_audit
        record_audit("OBSERVABILITY_ENABLED", {})
    except Exception:
        pass


def disable():
    try:
        from .production_seal import is_sealed
        if is_sealed():
            return
    except Exception:
        pass
    global OBSERVABILITY_ENABLED
    OBSERVABILITY_ENABLED = False
    try:
        from .audit_log import record_audit
        record_audit("OBSERVABILITY_DISABLED", {})
    except Exception:
        pass
