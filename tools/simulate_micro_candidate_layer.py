import os
import sys
import json
import sqlite3
import time
import argparse

def get_db_connection(db_path):
    db_uri = f"file:{db_path}?mode=ro"
    try:
        return sqlite3.connect(db_uri, uri=True)
    except sqlite3.OperationalError:
        return sqlite3.connect(db_path)

def load_source_data(conn, source_id):
    cursor = conn.cursor()
    
    # 1. Source verification
    cursor.execute("SELECT source_id, title, duration FROM sources WHERE source_id = ?;", (source_id,))
    row = cursor.fetchone()
    if not row:
        return None
    source_duration = row[2]
    title = row[1]
    
    # 2. Get semantic fragments
    cursor.execute("""
        SELECT id, fragment_id, start, end, semantic_json, structural_json, continuity_json 
        FROM semantic_fragments 
        WHERE source_id = ? 
        ORDER BY start;
    """, (source_id,))
    semantic_fragments = []
    for r in cursor.fetchall():
        semantic_fragments.append({
            "id": r[0],
            "fragment_id": r[1],
            "start": r[2],
            "end": r[3],
            "semantic_json": json.loads(r[4]) if r[4] else {},
            "structural_json": json.loads(r[5]) if r[5] else {},
            "continuity_json": json.loads(r[6]) if r[6] else {}
        })
        
    # 3. Get evidence board entries
    cursor.execute("""
        SELECT fragment_id, start, end, text, audio_energy, silence, scene_change, motion_score, speaker, keyframe, metadata_json
        FROM evidence_board
        WHERE source_id = ?
        ORDER BY start;
    """, (source_id,))
    evidence_board = []
    for r in cursor.fetchall():
        evidence_board.append({
            "fragment_id": r[0],
            "start": r[1],
            "end": r[2],
            "text": r[3] or "",
            "audio_energy": r[4] or 0.0,
            "silence": json.loads(r[5]) if r[5] else None,
            "scene_change": json.loads(r[6]) if r[6] else [],
            "motion_score": r[7] or 0.0,
            "speaker": r[8],
            "keyframe": r[9],
            "metadata_json": json.loads(r[10]) if r[10] else {}
        })
        
    # 4. Get transcript words
    cursor.execute("""
        SELECT fragment_id, start_time, end_time, intelligence 
        FROM fragments 
        WHERE source_id = ?;
    """, (source_id,))
    words = []
    for r in cursor.fetchall():
        intel = json.loads(r[3]) if r[3] else {}
        frag_words = intel.get("words", [])
        for w in frag_words:
            words.append({
                "word": w.get("word", ""),
                "start": w.get("start", 0.0),
                "end": w.get("end", 0.0),
                "probability": w.get("probability", 1.0)
            })
            
    # Fallback to subtitles segments
    if not words:
        cursor.execute("SELECT segments FROM subtitles WHERE source_id = ?;", (source_id,))
        sub_rows = cursor.fetchall()
        for s_row in sub_rows:
            if s_row[0]:
                segs = json.loads(s_row[0])
                for seg in segs:
                    if "words" in seg:
                        for w in seg["words"]:
                            words.append({
                                "word": w.get("word", ""),
                                "start": w.get("start", 0.0),
                                "end": w.get("end", 0.0),
                                "probability": w.get("probability", 1.0)
                            })
                    else:
                        words.append({
                            "word": seg.get("text", ""),
                            "start": seg.get("start", 0.0),
                            "end": seg.get("end", 0.0),
                            "probability": 1.0
                        })
            
    words.sort(key=lambda x: x["start"])
    
    return {
        "source_id": source_id,
        "title": title,
        "source_duration": source_duration,
        "semantic_fragments": semantic_fragments,
        "evidence_board": evidence_board,
        "words": words
    }

def split_to_micro_candidates(parent_frag, evidence_board):
    p_start = parent_frag["start"]
    p_end = parent_frag["end"]
    p_id = parent_frag["id"]
    
    # scene change lists
    scene_changes = []
    for eb in evidence_board:
        if eb["scene_change"]:
            for sc in eb["scene_change"]:
                if p_start <= sc <= p_end:
                    scene_changes.append(sc)
                    
    scene_changes = sorted(list(set(scene_changes)))
    
    candidates = []
    curr = p_start
    candidate_idx = 1
    
    while curr < p_end:
        min_end = curr + 2.0
        max_end = curr + 6.0
        
        if p_end <= min_end:
            candidates.append({
                "candidate_id": f"MC_{p_id}_{candidate_idx:03d}",
                "parent_id": p_id,
                "start": curr,
                "end": p_end,
                "duration": p_end - curr
            })
            break
            
        valid_scs = [sc for sc in scene_changes if min_end <= sc <= max_end]
        
        if valid_scs:
            c_end = valid_scs[-1]
        else:
            c_end = min(p_end, curr + 4.0)
            
        if p_end - c_end < 2.0:
            c_end = p_end
            
        candidates.append({
            "candidate_id": f"MC_{p_id}_{candidate_idx:03d}",
            "parent_id": p_id,
            "start": curr,
            "end": c_end,
            "duration": c_end - curr
        })
        
        curr = c_end
        candidate_idx += 1
        
    return candidates

def calculate_candidate_scores(candidate, data):
    c_start = candidate["start"]
    c_end = candidate["end"]
    c_dur = candidate["duration"]
    
    # 1. Speech Score
    speech_duration = 0.0
    overlapping_words = []
    for w in data["words"]:
        w_start = w["start"]
        w_end = w["end"]
        if w_start < c_end and w_end > c_start:
            overlap = min(w_end, c_end) - max(w_start, c_start)
            if overlap > 0:
                speech_duration += overlap
                overlapping_words.append(w)
                
    speech_score = min(1.0, speech_duration / c_dur) if c_dur > 0 else 0.0
    text_sample = " ".join([w["word"].strip() for w in overlapping_words])
    text_exists = len(text_sample) > 0
    
    # 2. Audio Energy & Silence
    silence_duration = 0.0
    avg_audio_energy = 0.0
    energy_count = 0
    evidence_count = 0
    keyframe_path = None
    scene_changes_in_candidate = []
    
    # Look for visual evidence indicators (e.g. face detection, yolo object tags)
    visual_human_detected = False
    visual_human_confidence = 0.0
    
    for eb in data["evidence_board"]:
        if eb["start"] < c_end and eb["end"] > c_start:
            evidence_count += 1
            avg_audio_energy += eb["audio_energy"]
            energy_count += 1
            if eb.get("keyframe"):
                keyframe_path = eb["keyframe"]
            if eb["scene_change"]:
                for sc in eb["scene_change"]:
                    if c_start <= sc <= c_end:
                        scene_changes_in_candidate.append(sc)
            if eb["silence"]:
                for s in eb["silence"]:
                    s_start = s.get("start", 0.0)
                    s_end = s.get("end", 0.0)
                    if s_start < c_end and s_end > c_start:
                        s_overlap = min(s_end, c_end) - max(s_start, c_start)
                        if s_overlap > 0:
                            silence_duration += s_overlap
                            
            # Inspect metadata_json or speaker for human indications
            meta = eb.get("metadata_json", {})
            # Look for keys containing "face", "person", "human", "yolo", "objects"
            for k, v in meta.items():
                if any(x in k.lower() for x in ["face", "person", "human", "yolo", "objects"]):
                    visual_human_detected = True
                    # estimate confidence
                    if isinstance(v, (int, float)):
                        visual_human_confidence = max(visual_human_confidence, float(v))
                    else:
                        visual_human_confidence = 1.0
            if eb.get("speaker"):
                # Speaker tag is also a form of human indicator
                visual_human_detected = True
                visual_human_confidence = 1.0
                
    avg_audio_energy = (avg_audio_energy / energy_count) if energy_count > 0 else 0.0
    scene_changes_in_candidate = sorted(list(set(scene_changes_in_candidate)))
    
    if silence_duration > 0:
        silence_score = min(1.0, silence_duration / c_dur)
    else:
        silence_score = max(0.0, 1.0 - (avg_audio_energy / 0.05))
        
    # 3. Motion
    avg_motion = 0.0
    motion_count = 0
    for eb in data["evidence_board"]:
         if eb["start"] < c_end and eb["end"] > c_start:
             avg_motion += eb["motion_score"]
             motion_count += 1
    motion_score_raw = (avg_motion / motion_count) if motion_count > 0 else 0.0
    motion_score_normalized = min(1.0, motion_score_raw / 0.5)
    
    # 4. Scenery (Static background: low speech, low motion, low energy)
    norm_audio = min(1.0, avg_audio_energy / 0.05)
    scenery_score = max(0.0, 1.0 - speech_score - (motion_score_normalized * 0.5) - (norm_audio * 0.5))
    
    # 5. Weak Human
    weak_human_score = 0.0
    if 0.0 < speech_score <= 0.35:
        weak_human_score = 1.0 - (speech_score / 0.35)
    elif speech_score == 0.0 and 0.01 <= avg_audio_energy <= 0.04:
        weak_human_score = max(0.0, min(1.0, 1.0 - (abs(avg_audio_energy - 0.025) / 0.015)))
        
    # 6. Highlight
    norm_energy_for_highlight = min(1.0, avg_audio_energy / 0.08)
    highlight_score = (motion_score_normalized * 0.4) + (norm_energy_for_highlight * 0.6)
    
    # 7. Filler
    filler_words = ["어", "음", "아", "그", "이제", "막", "그니까", "어음"]
    filler_count = 0
    for w in overlapping_words:
        cleaned_word = w["word"].strip().lower()
        if any(f in cleaned_word for f in filler_words):
            filler_count += 1
    filler_score = min(1.0, filler_count / 3.0)
    if filler_score == 0.0 and silence_score > 0.8:
        filler_score = silence_score * 0.3
        
    # Determine tag reason
    reasons = []
    if speech_score > 0.4:
        reasons.append("Active Speech")
    if visual_human_detected:
        reasons.append("Visual Human Found")
    if scenery_score > 0.7:
        reasons.append("Static Scenery")
    if silence_score > 0.7:
        reasons.append("Silent Pause")
    if highlight_score > 0.6:
        reasons.append("Highlight Peak")
    if filler_score > 0.5:
        reasons.append("Filler Gap")
        
    tag_reason = ", ".join(reasons) if reasons else "General B-Roll"
    
    return {
        "text_exists": text_exists,
        "text_sample": text_sample,
        "evidence_count": evidence_count,
        "motion_score_raw": motion_score_raw,
        "silence_raw": silence_duration,
        "scene_change_raw": scene_changes_in_candidate,
        "keyframe_exists": keyframe_path is not None,
        "keyframe_path": keyframe_path,
        "visual_human_detected": visual_human_detected,
        "visual_human_confidence": visual_human_confidence,
        "speech_score": speech_score,
        "motion_score_normalized": motion_score_normalized,
        "scenery_score": scenery_score,
        "weak_human_score": weak_human_score,
        "highlight_score": highlight_score,
        "filler_score": filler_score,
        "tag_reason": tag_reason
    }

def calculate_intent_scores_for_candidate(c, intent_name, count_selected_from_same_parent=0, count_selected_from_same_source=0):
    base_score = 0.5
    sp = c["scores"]["speech_score"]
    mo = c["scores"]["motion_score_normalized"]
    sc = c["scores"]["scenery_score"]
    wh = c["scores"]["weak_human_score"]
    vh = c["scores"].get("visual_human_confidence", 0.0)
    fi = c["scores"]["filler_score"]
    dur = c["duration"]
    
    silence_normalized = (c["scores"]["silence_raw"] / dur) if c["scores"]["silence_raw"] > 0 else max(0.0, 1.0 - c["scores"]["highlight_score"])
    
    score = base_score
    formula = ""
    
    if intent_name == "speech_human_priority":
        score = base_score * 0.2 + sp * 0.5 + wh * 0.3 - sc * 0.2 - fi * 0.3
        formula = f"base(0.5)*0.2 + speech({sp:.2f})*0.5 + weak_human({wh:.2f})*0.3 - scenery({sc:.2f})*0.2 - filler({fi:.2f})*0.3"
    elif intent_name == "visual_human_priority":
        score = base_score * 0.2 + vh * 0.8
        formula = f"base(0.5)*0.2 + visual_human({vh:.2f})*0.8"
    elif intent_name == "reduce_scenery":
        score = base_score * 0.2 + sp * 0.3 + mo * 0.3 + (1.0 - sc) * 0.5
        formula = f"base(0.5)*0.2 + speech({sp:.2f})*0.3 + motion({mo:.2f})*0.3 + (1.0 - scenery({sc:.2f}))*0.5"
    elif intent_name == "fast_pace":
        len_factor = 1.0 - (dur - 2.0) / 4.0
        score = base_score * 0.1 + mo * 0.4 + (1.0 - silence_normalized) * 0.3 + len_factor * 0.2
        formula = f"base(0.5)*0.1 + motion({mo:.2f})*0.4 + (1.0 - silence({silence_normalized:.2f}))*0.3 + len_factor({len_factor:.2f})*0.2"
    elif intent_name == "balanced_sources":
        score = base_score - (0.3 * count_selected_from_same_parent) - (0.4 * count_selected_from_same_source)
        formula = f"base(0.5) - parent_penalty(0.3 * {count_selected_from_same_parent}) - source_penalty(0.4 * {count_selected_from_same_source})"
        
    return score, formula

def simulate_coarse_selection(parent_fragments, data, intent_name, target_length=30.0):
    coarse_items = []
    for pf in parent_fragments:
        p_start = pf["start"]
        p_end = pf["end"]
        p_dur = p_end - p_start
        
        # Motion
        m_vals = [eb["motion_score"] for eb in data["evidence_board"] if eb["start"] < p_end and eb["end"] > p_start]
        avg_motion = sum(m_vals)/len(m_vals) if m_vals else 0.0
        
        # Speech
        speech_dur = 0.0
        for w in data["words"]:
            if w["start"] < p_end and w["end"] > p_start:
                overlap = min(w["end"], p_end) - max(w["start"], p_start)
                if overlap > 0:
                    speech_dur += overlap
        speech_ratio = speech_dur / p_dur if p_dur > 0 else 0.0
        
        # Audio Energy
        e_vals = [eb["audio_energy"] for eb in data["evidence_board"] if eb["start"] < p_end and eb["end"] > p_start]
        avg_energy = sum(e_vals)/len(e_vals) if e_vals else 0.0
        norm_audio = min(1.0, avg_energy / 0.05)
        
        # Scenery
        scenery_ratio = max(0.0, 1.0 - speech_ratio - (avg_motion * 0.5) - (norm_audio * 0.5))
        
        # Weak human & visual human estimation
        weak_human_score = 0.0
        if 0.0 < speech_ratio <= 0.35:
            weak_human_score = 1.0 - (speech_ratio / 0.35)
        elif speech_ratio == 0.0 and 0.01 <= avg_energy <= 0.04:
            weak_human_score = max(0.0, min(1.0, 1.0 - (abs(avg_energy - 0.025) / 0.015)))
            
        visual_human_confidence = 0.0
        for eb in data["evidence_board"]:
            if eb["start"] < p_end and eb["end"] > p_start:
                meta = eb.get("metadata_json", {})
                for k, v in meta.items():
                    if any(x in k.lower() for x in ["face", "person", "human", "yolo", "objects"]):
                        if isinstance(v, (int, float)):
                            visual_human_confidence = max(visual_human_confidence, float(v))
                        else:
                            visual_human_confidence = 1.0
                if eb.get("speaker"):
                    visual_human_confidence = 1.0
                    
        score = 0.5
        if intent_name == "speech_human_priority":
            score = 0.2 + speech_ratio * 0.5 + weak_human_score * 0.3 - scenery_ratio * 0.2
        elif intent_name == "visual_human_priority":
            score = 0.2 + visual_human_confidence * 0.8
        elif intent_name == "reduce_scenery":
            score = 0.2 + speech_ratio * 0.3 + avg_motion * 0.3 + (1.0 - scenery_ratio) * 0.5
        elif intent_name == "fast_pace":
            score = 0.5 + avg_motion * 0.5
        elif intent_name == "balanced_sources":
            score = 0.5
            
        coarse_items.append({
            "id": pf["id"],
            "start": p_start,
            "end": p_end,
            "duration": p_dur,
            "score": score,
            "motion": avg_motion,
            "speech": speech_ratio,
            "scenery": scenery_ratio,
            "weak_human": weak_human_score,
            "visual_human": visual_human_confidence
        })
        
    selected = []
    current_length = 0.0
    
    if intent_name == "balanced_sources":
        coarse_items_sorted = sorted(coarse_items, key=lambda x: x["start"])
        for item in coarse_items_sorted:
            if current_length < target_length:
                selected.append(item)
                current_length += item["duration"]
    else:
        coarse_items_sorted = sorted(coarse_items, key=lambda x: x["score"], reverse=True)
        for item in coarse_items_sorted:
            if current_length < target_length:
                selected.append(item)
                current_length += item["duration"]
                
    if not selected:
        return {"selected_ids": [], "total_duration": 0.0, "avg_motion": 0.0, "avg_speech": 0.0, "avg_scenery": 0.0, "avg_weak_human": 0.0, "avg_visual_human": 0.0, "clip_count": 0, "avg_clip_duration": 0.0}
        
    tot_dur = sum(item["duration"] for item in selected)
    avg_m = sum(item["motion"] * item["duration"] for item in selected) / tot_dur
    avg_sp = sum(item["speech"] * item["duration"] for item in selected) / tot_dur
    avg_sc = sum(item["scenery"] * item["duration"] for item in selected) / tot_dur
    avg_wh = sum(item["weak_human"] * item["duration"] for item in selected) / tot_dur
    avg_vh = sum(item["visual_human"] * item["duration"] for item in selected) / tot_dur
    
    return {
        "selected_ids": [item["id"] for item in selected],
        "total_duration": tot_dur,
        "avg_motion": avg_m,
        "avg_speech": avg_sp,
        "avg_scenery": avg_sc,
        "avg_weak_human": avg_wh,
        "avg_visual_human": avg_vh,
        "clip_count": len(selected),
        "avg_clip_duration": tot_dur / len(selected)
    }

def simulate_micro_selection(candidates, intent_name, target_length=30.0):
    selected = []
    current_length = 0.0
    
    available = []
    for c in candidates:
        score, formula = calculate_intent_scores_for_candidate(c, intent_name)
        available.append({
            "candidate": c,
            "score": score,
            "original_score": score
        })
        
    while current_length < target_length and available:
        if intent_name == "balanced_sources":
            parent_counts = {}
            for sel in selected:
                p_id = sel["candidate"]["parent_id"]
                parent_counts[p_id] = parent_counts.get(p_id, 0) + 1
                
            for av in available:
                p_id = av["candidate"]["parent_id"]
                score, _ = calculate_intent_scores_for_candidate(av["candidate"], intent_name, count_selected_from_same_parent=parent_counts.get(p_id, 0))
                av["score"] = score
                
        available.sort(key=lambda x: x["score"], reverse=True)
        best = available.pop(0)
        selected.append(best)
        current_length += best["candidate"]["duration"]
        
    if not selected:
        return {"selected_ids": [], "total_duration": 0.0, "avg_motion": 0.0, "avg_speech": 0.0, "avg_scenery": 0.0, "avg_weak_human": 0.0, "avg_visual_human": 0.0, "clip_count": 0, "avg_clip_duration": 0.0, "selection_reason": "No candidates available"}
        
    tot_dur = sum(item["candidate"]["duration"] for item in selected)
    avg_m = sum(item["candidate"]["scores"]["motion_score_normalized"] * item["candidate"]["duration"] for item in selected) / tot_dur
    avg_sp = sum(item["candidate"]["scores"]["speech_score"] * item["candidate"]["duration"] for item in selected) / tot_dur
    avg_sc = sum(item["candidate"]["scores"]["scenery_score"] * item["candidate"]["duration"] for item in selected) / tot_dur
    avg_wh = sum(item["candidate"]["scores"]["weak_human_score"] * item["candidate"]["duration"] for item in selected) / tot_dur
    avg_vh = sum(item["candidate"]["scores"].get("visual_human_confidence", 0.0) * item["candidate"]["duration"] for item in selected) / tot_dur
    
    reason_parts = [
        f"Selected {len(selected)} clips totaling {tot_dur:.2f}s (target {target_length}s).",
        f"Avg speech: {avg_sp:.2%}, scenery: {avg_sc:.2%}, weak human: {avg_wh:.2%}, visual human: {avg_vh:.2%}."
    ]
    if intent_name == "speech_human_priority":
        reason_parts.append("Prioritized ASR text speech ratio & weak human voice cues, penalized filler words and scenery.")
    elif intent_name == "visual_human_priority":
        reason_parts.append("Prioritized visual human features (such as faces or speaker detections).")
    elif intent_name == "reduce_scenery":
        reason_parts.append("Prioritized motion and speech presence, heavily penalized scenic static background clips.")
    elif intent_name == "fast_pace":
        reason_parts.append("Prioritized shorter clip durations and active audio/motion energy segments.")
    elif intent_name == "balanced_sources":
        reason_parts.append("Dynamically penalized repetitive parent fragments to distribute selections evenly.")
        
    return {
        "selected_ids": [item["candidate"]["candidate_id"] for item in selected],
        "total_duration": tot_dur,
        "avg_motion": avg_m,
        "avg_speech": avg_sp,
        "avg_scenery": avg_sc,
        "avg_weak_human": avg_wh,
        "avg_visual_human": avg_vh,
        "clip_count": len(selected),
        "avg_clip_duration": tot_dur / len(selected),
        "selection_reason": " ".join(reason_parts)
    }

def simulate_project_level_layer(conn, target_length=60.0):
    cursor = conn.cursor()
    cursor.execute("SELECT source_id FROM sources WHERE duration > 0.0;")
    source_ids = [row[0] for row in cursor.fetchall()]
    
    if len(source_ids) < 2:
        return {
            "project_level_success": False,
            "fail_reason": "single_source_only",
            "unique_source_count": len(source_ids),
            "selected_clips": [],
            "source_distribution": {}
        }
        
    all_project_candidates = []
    
    # Generate micro candidates for all sources and pool them together
    for sid in source_ids:
        data = load_source_data(conn, sid)
        if not data:
            continue
        for pf in data["semantic_fragments"]:
            pf_candidates = split_to_micro_candidates(pf, data["evidence_board"])
            for c in pf_candidates:
                c["source_id"] = sid
                c["parent_semantic_fragment_id"] = pf["id"]
                c["scores"] = calculate_candidate_scores(c, data)
                all_project_candidates.append(c)
                
    if not all_project_candidates:
        return {
            "project_level_success": False,
            "fail_reason": "no_candidates_generated",
            "unique_source_count": len(source_ids),
            "selected_clips": [],
            "source_distribution": {}
        }
        
    # Run a selection simulation using "balanced_sources" project-level logic
    # penalizes repetitive selections from the same parent AND same source_id
    selected = []
    current_length = 0.0
    
    available = []
    for c in all_project_candidates:
        score, formula = calculate_intent_scores_for_candidate(c, "balanced_sources")
        available.append({
            "candidate": c,
            "score": score,
            "original_score": score
        })
        
    while current_length < target_length and available:
        parent_counts = {}
        source_counts = {}
        for sel in selected:
            p_id = sel["candidate"]["parent_id"]
            s_id = sel["candidate"]["source_id"]
            parent_counts[p_id] = parent_counts.get(p_id, 0) + 1
            source_counts[s_id] = source_counts.get(s_id, 0) + 1
            
        for av in available:
            p_id = av["candidate"]["parent_id"]
            s_id = av["candidate"]["source_id"]
            score, _ = calculate_intent_scores_for_candidate(
                av["candidate"], 
                "balanced_sources", 
                count_selected_from_same_parent=parent_counts.get(p_id, 0),
                count_selected_from_same_source=source_counts.get(s_id, 0)
            )
            av["score"] = score
            
        available.sort(key=lambda x: x["score"], reverse=True)
        best = available.pop(0)
        selected.append(best)
        current_length += best["candidate"]["duration"]
        
    # Analyze source distribution
    source_distribution = {}
    for sel in selected:
        s_id = sel["candidate"]["source_id"]
        source_distribution[s_id] = source_distribution.get(s_id, 0.0) + sel["candidate"]["duration"]
        
    tot_selected_dur = sum(item["candidate"]["duration"] for item in selected)
    distribution_details = {}
    for sid, dur in source_distribution.items():
        distribution_details[sid] = {
            "duration": dur,
            "ratio": dur / tot_selected_dur if tot_selected_dur > 0 else 0.0
        }
        
    unique_selected_sources = len(source_distribution)
    diversity_score = unique_selected_sources / len(source_ids) if source_ids else 0.0
    
    project_level_success = unique_selected_sources >= 2
    
    return {
        "project_level_success": project_level_success,
        "total_selected_duration": tot_selected_dur,
        "unique_source_count": len(source_ids),
        "selected_source_count": unique_selected_sources,
        "diversity_score": diversity_score,
        "source_distribution": distribution_details,
        "selected_clips": [item["candidate"]["candidate_id"] for item in selected]
    }

def main():
    parser = argparse.ArgumentParser(description="CCUT Step 2-G-R2: Micro Candidate Feasibility Simulator v0.2")
    parser.add_argument("--db", default="ccut_backend/ccut_app.db", help="Path to ccut_app.db")
    parser.add_argument("--source_id", default=None, help="Source ID to simulate. If omitted, uses latest source.")
    parser.add_argument("--target_len", type=float, default=30.0, help="Target edited video length in seconds.")
    args = parser.parse_args()
    
    db_path = args.db
    if not os.path.exists(db_path):
        print(f"[Error] Database file not found at: {db_path}")
        sys.exit(1)
        
    t_gen_start = time.perf_counter()
    
    conn = get_db_connection(db_path)
    try:
        # Check total sources count in project
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sources WHERE duration > 0.0;")
        project_sources_count = cursor.fetchone()[0]
        
        # Load single source
        data = load_source_data(conn, args.source_id)
        if not data:
            print("[Error] Failed to load data from database.")
            sys.exit(1)
            
        source_id = data["source_id"]
        source_duration = data["source_duration"]
        semantic_fragments = data["semantic_fragments"]
        evidence_board = data["evidence_board"]
        
        # Step 1: Generate candidates
        all_candidates = []
        for pf in semantic_fragments:
            pf_candidates = split_to_micro_candidates(pf, evidence_board)
            for c in pf_candidates:
                c["source_id"] = source_id
                c["parent_semantic_fragment_id"] = pf["id"]
                c["scores"] = calculate_candidate_scores(c, data)
                all_candidates.append(c)
                
        t_gen_end = time.perf_counter()
        generation_time = t_gen_end - t_gen_start
        
        if not all_candidates:
            print("[Error] Generated 0 micro candidates. Feasibility simulation failed.")
            sys.exit(1)
            
        # Step 2: Simulate re-scoring & selection with high-resolution timer
        t_score_start = time.perf_counter()
        
        intents = [
            "speech_human_priority",
            "visual_human_priority",
            "reduce_scenery",
            "fast_pace",
            "balanced_sources"
        ]
        intent_results = {}
        coarse_vs_micro_comparison = {}
        
        for intent in intents:
            coarse_res = simulate_coarse_selection(semantic_fragments, data, intent, args.target_len)
            micro_res = simulate_micro_selection(all_candidates, intent, args.target_len)
            
            intent_results[intent] = {
                "coarse": coarse_res,
                "micro": micro_res
            }
            
            coarse_vs_micro_comparison[intent] = {
                "duration_diff": micro_res["total_duration"] - coarse_res["total_duration"],
                "motion_improvement": micro_res["avg_motion"] - coarse_res["avg_motion"],
                "speech_ratio_improvement": micro_res["avg_speech"] - coarse_res["avg_speech"],
                "weak_human_score_improvement": micro_res["avg_weak_human"] - coarse_res["avg_weak_human"],
                "visual_human_score_improvement": micro_res["avg_visual_human"] - coarse_res["avg_visual_human"],
                "scenery_reduction": coarse_res["avg_scenery"] - micro_res["avg_scenery"],
                "clip_duration_reduction_ratio": (coarse_res["avg_clip_duration"] - micro_res["avg_clip_duration"]) / coarse_res["avg_clip_duration"] if coarse_res["avg_clip_duration"] > 0 else 0.0
            }
            
        t_score_end = time.perf_counter()
        scoring_time = t_score_end - t_score_start
        
        # Step 3: Run project-level simulation
        project_simulation_res = simulate_project_level_layer(conn)
        
        # Step 4: Evaluate constraints and statuses
        # 4.1 Speech human priority signal sufficiency check
        total_words = len(data["words"])
        speech_insufficient = total_words == 0
        
        # 4.2 Visual human priority signal sufficiency check (Always insufficient if no visual indicators exist)
        has_any_visual_evidence = any(c["scores"]["visual_human_detected"] for c in all_candidates)
        visual_insufficient = not has_any_visual_evidence
        
        # Determine global data insufficiency
        data_insufficient = speech_insufficient or visual_insufficient
        
        # Check if selected candidates are identical across all intents
        first_intent_ids = intent_results[intents[0]]["micro"]["selected_ids"]
        all_same = True
        for intent in intents[1:]:
            if intent_results[intent]["micro"]["selected_ids"] != first_intent_ids:
                all_same = False
                break
        
        intent_not_distinguishable = False
        fail_reasons = []
        if all_same:
            intent_not_distinguishable = True
            fail_reasons.append("identical_results_across_intents")
        if speech_insufficient:
            fail_reasons.append("speech_human_priority_insufficient_data")
        if visual_insufficient:
            fail_reasons.append("visual_human_priority_no_visual_evidence")
            
        # 4.3 reduce_scenery 효과성 판정 (scenery_reduction_effect)
        scenery_reduction_raw = coarse_vs_micro_comparison["reduce_scenery"]["scenery_reduction"]
        if scenery_reduction_raw < 0.1:
            scenery_reduction_effect = "WEAK_EFFECT"
        else:
            scenery_reduction_effect = "STRONG_EFFECT"
            
        # 4.4 fast_pace 결과 판정 (pace_success)
        pace_reduction_ratio = coarse_vs_micro_comparison["fast_pace"]["clip_duration_reduction_ratio"]
        micro_clip_dur = intent_results["fast_pace"]["micro"]["avg_clip_duration"]
        # success if clip duration is reduced by > 30% OR absolute micro duration is <= 5.0s
        pace_success = (pace_reduction_ratio >= 0.3 or micro_clip_dur <= 5.0)
        
        # 4.5 balanced_sources 단일 소스 제한 (balanced_success)
        balanced_success = project_sources_count >= 2
        
        # Format the candidates output structure cleanly for human verification
        formatted_candidates = []
        for c in all_candidates:
            # build calculation logs per intent
            log_speech, form_speech = calculate_intent_scores_for_candidate(c, "speech_human_priority")
            log_visual, form_visual = calculate_intent_scores_for_candidate(c, "visual_human_priority")
            log_scenery, form_scenery = calculate_intent_scores_for_candidate(c, "reduce_scenery")
            log_pace, form_pace = calculate_intent_scores_for_candidate(c, "fast_pace")
            log_balance, form_balance = calculate_intent_scores_for_candidate(c, "balanced_sources")
            
            formatted_candidates.append({
                "candidate_id": c["candidate_id"],
                "parent_semantic_fragment_id": c["parent_semantic_fragment_id"],
                "source_id": c["source_id"],
                "time_range": f"{c['start']:.2f}s - {c['end']:.2f}s (duration: {c['duration']:.2f}s)",
                "text_match_summary": f"Contains {len([w for w in data['words'] if w['start'] < c['end'] and w['end'] > c['start']])} words. Sample: '{c['scores']['text_sample']}'" if c['scores']['text_exists'] else "No text transcription matches.",
                "visual_signals": {
                    "keyframe_exists": c["scores"]["keyframe_exists"],
                    "keyframe_path": c["scores"]["keyframe_path"],
                    "scene_changes_detected": c["scores"]["scene_change_raw"],
                    "visual_human_detected": c["scores"]["visual_human_detected"],
                    "visual_human_confidence": c["scores"]["visual_human_confidence"]
                },
                "raw_measurements": {
                    "motion_score_raw": c["scores"]["motion_score_raw"],
                    "silence_duration_raw": c["scores"]["silence_raw"],
                    "evidence_count": c["scores"]["evidence_count"]
                },
                "normalized_scores": {
                    "speech_score": c["scores"]["speech_score"],
                    "motion_score_normalized": c["scores"]["motion_score_normalized"],
                    "scenery_score": c["scores"]["scenery_score"],
                    "weak_human_score": c["scores"]["weak_human_score"],
                    "highlight_score": c["scores"]["highlight_score"],
                    "filler_score": c["scores"]["filler_score"]
                },
                "tag_reason": c["scores"]["tag_reason"],
                "score_details_per_intent": {
                    "speech_human_priority": {
                        "score": log_speech,
                        "calculation_log": form_speech
                    },
                    "visual_human_priority": {
                        "score": log_visual,
                        "calculation_log": form_visual
                    },
                    "reduce_scenery": {
                        "score": log_scenery,
                        "calculation_log": form_scenery
                    },
                    "fast_pace": {
                        "score": log_pace,
                        "calculation_log": form_pace
                    },
                    "balanced_sources": {
                        "score": log_balance,
                        "calculation_log": form_balance
                    }
                }
            })
            
        score_formulas = {
            "speech_human_priority": "base_score * 0.2 + speech_score * 0.5 + weak_human_score * 0.3 - scenery_score * 0.2 - filler_score * 0.3",
            "visual_human_priority": "base_score * 0.2 + visual_human_confidence * 0.8",
            "reduce_scenery": "base_score * 0.2 + speech_score * 0.3 + motion_score_normalized * 0.3 + (1.0 - scenery_score) * 0.5",
            "fast_pace": "base_score * 0.1 + motion_score_normalized * 0.4 + (1.0 - silence_normalized) * 0.3 + (1.0 - (duration - 2.0) / 4.0) * 0.2",
            "balanced_sources": "base_score - (0.3 * count_selected_from_same_parent) - (0.4 * count_selected_from_same_source)"
        }
        
        candidates_json_str = json.dumps(formatted_candidates, ensure_ascii=False)
        estimated_json_kb = len(candidates_json_str.encode('utf-8')) / 1024.0
        
        output_data = {
            "source_id": source_id,
            "source_duration": source_duration,
            "parent_semantic_fragment_count": len(semantic_fragments),
            "micro_candidate_count": len(all_candidates),
            "candidates_per_parent": len(all_candidates) / len(semantic_fragments) if len(semantic_fragments) > 0 else 0.0,
            "generation_time_sec": generation_time,
            "scoring_time_sec": scoring_time,
            "estimated_json_kb": estimated_json_kb,
            "intent_not_distinguishable": intent_not_distinguishable,
            "fail_reasons": fail_reasons,
            "data_insufficient": data_insufficient,
            "speech_insufficient": speech_insufficient,
            "visual_insufficient": visual_insufficient,
            "scenery_reduction_effect": scenery_reduction_effect,
            "pace_success": pace_success,
            "balanced_success": balanced_success,
            "score_formulas": score_formulas,
            "intent_results": intent_results,
            "coarse_vs_micro_comparison": coarse_vs_micro_comparison,
            "project_level_simulation": project_simulation_res,
            "micro_candidates": formatted_candidates,
            "schema_used": {
                "sources": ["source_id", "duration", "title"],
                "semantic_fragments": ["id", "fragment_id", "start", "end", "semantic_json", "structural_json", "continuity_json"],
                "evidence_board": ["fragment_id", "start", "end", "scene_change", "motion_score", "audio_energy", "silence", "speaker", "keyframe", "metadata_json"],
                "fragments": ["intelligence"],
                "subtitles": ["segments"]
            }
        }
        
        artifacts_dir = "artifacts/micro_candidate_simulation"
        os.makedirs(artifacts_dir, exist_ok=True)
        out_file = os.path.join(artifacts_dir, f"{source_id}.json")
        
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        print(f"[Success v0.2] Simulation written: {out_file}")
        print(f" - Micro Candidate Count: {len(all_candidates)}")
        print(f" - Speech Insufficient: {speech_insufficient}")
        print(f" - Visual Insufficient: {visual_insufficient}")
        print(f" - Scenery Reduction Effect: {scenery_reduction_effect}")
        print(f" - Fast Pace Success: {pace_success}")
        print(f" - Balanced Success (Project has >=2 videos): {balanced_success}")
        print(f" - Project-Level Simulation success: {project_simulation_res['project_level_success']}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
