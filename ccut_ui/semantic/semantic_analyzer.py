def suggest_groups(fragments: list) -> list:
    groups = []

    for i in range(len(fragments) - 1):
        a, b = fragments[i], fragments[i + 1]
        groups.append({
            "id": f"sg_adj_{i}",
            "type": "CONTIGUOUS",
            "ids": [a["id"], b["id"]],
            "reason": "Adjacent timeline fragments",
        })

    short_threshold = 3.0
    for frag in fragments:
        if frag["duration"] < short_threshold:
            idx = next((j for j, f in enumerate(fragments) if f["id"] == frag["id"]), -1)
            neighbor_id = fragments[idx - 1]["id"] if idx > 0 else (
                fragments[idx + 1]["id"] if idx < len(fragments) - 1 else None
            )
            if neighbor_id:
                sg_id = f"sg_short_{frag['id']}"
                if not any(g["id"] == sg_id for g in groups):
                    groups.append({
                        "id": sg_id,
                        "type": "SHORT_MERGE",
                        "ids": [neighbor_id, frag["id"]],
                        "reason": f"Fragment '{frag['id']}' is short ({frag['duration']}s)",
                    })

    return groups
