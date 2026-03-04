def map_projection_to_fragments(projection: dict) -> list:
    cuts = projection.get("cuts", {})
    fragments = []

    if isinstance(cuts, dict):
        for cut_id, cut_data in cuts.items():
            if isinstance(cut_data, dict):
                start = float(cut_data.get("start", 0))
                end = float(cut_data.get("end", start))
            else:
                start, end = 0.0, 1.0
            fragments.append({
                "id": cut_id,
                "start": start,
                "end": end,
                "duration": round(end - start, 4),
            })
    elif isinstance(cuts, list):
        for cut in cuts:
            if isinstance(cut, dict):
                start = float(cut.get("start", 0))
                end = float(cut.get("end", start))
                fragments.append({
                    "id": cut.get("id", "?"),
                    "start": start,
                    "end": end,
                    "duration": round(end - start, 4),
                })

    return sorted(fragments, key=lambda f: f["start"])
