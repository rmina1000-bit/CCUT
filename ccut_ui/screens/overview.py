from adapters.engine_read_adapter import read_status, read_verify, read_seal, read_audit


def build_overview() -> dict:
    return {
        "status": read_status(),
        "verify": read_verify(),
        "sealed": read_seal(),
        "audit_tail": read_audit(5),
    }
