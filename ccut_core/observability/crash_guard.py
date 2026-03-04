import atexit
import signal
from .trace_buffer import flush_all


def _flush_on_exit(*args):
    try:
        flush_all()
    except Exception:
        pass


def register_crash_guard():
    try:
        atexit.register(_flush_on_exit)
        signal.signal(signal.SIGINT, _flush_on_exit)
        signal.signal(signal.SIGTERM, _flush_on_exit)
    except Exception:
        pass
