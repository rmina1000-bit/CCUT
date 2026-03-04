def get_engine_status(log):
    from verify import verify_log

    events = log.get_events()
    audit = verify_log(events)

    return {
        "engine_id": events[0]["payload"]["engine_id"],
        "created_at": events[0]["payload"]["created_at"],
        "event_count": audit["event_count"],
        "last_hash": audit["last_hash"],
        "valid": audit["valid"]
    }
