ALLOWED_TYPES = {"CREATE_CUT", "DELETE_CUT", "SPLIT", "MERGE"}


def send_command(command: dict) -> dict:
    cmd_type = command.get("type", "")

    if cmd_type not in ALLOWED_TYPES:
        return {
            "error": f"command type '{cmd_type}' not allowed",
            "allowed": sorted(ALLOWED_TYPES),
        }

    try:
        from decision_log import DecisionLog
        log = DecisionLog()
        log.append(cmd_type, command.get("payload", {}))
        return {"ok": True, "type": cmd_type, "seq": log._seq}
    except Exception as e:
        return {"ok": False, "error": str(e)}
