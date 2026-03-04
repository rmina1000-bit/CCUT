try:
    from .crash_guard import register_crash_guard
    register_crash_guard()
except Exception:
    pass
