SEALED: bool = False


def is_sealed() -> bool:
    return SEALED


def seal():
    global SEALED
    if SEALED:
        return

    SEALED = True

    try:
        from .runtime_switch import enable
        enable()
    except Exception:
        pass

    try:
        from .audit_log import record_audit
        record_audit("PRODUCTION_SEAL_APPLIED", {})
    except Exception:
        pass
