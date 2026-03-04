import json
from datetime import datetime, timezone
from pathlib import Path


AUDIT_DIR = Path("storage/observability")
AUDIT_LOG = AUDIT_DIR / "audit.log"


def record_audit(event_type: str, details: dict = None):
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details or {},
        }

        line = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
