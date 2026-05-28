from database import SessionLocal
from .learning_models import WeakLabelTable

class WeakLabelGenerator:
    """
    [STEP 14-B] WeakLabelGenerator
    Applies heuristic labeling functions (LFs) based on audio, motion, and transcripts
    to generate weak training signals without manual human labeling (Snorkel style).
    """

    @staticmethod
    def generate_labels_for_fragment(fragment: dict, source_id: str) -> list:
        """
        Analyzes semantic, structural, and evidence signals to generate weak labels.
        """
        fid = fragment.get("fragment_id") or fragment.get("id")
        if not fid:
            return []

        # Resolve actual details from database tables if missing
        role = fragment.get("structural", {}).get("role", "main")
        start_time = float(fragment.get("start") or fragment.get("start_time") or 0.0)
        
        duration = fragment.get("duration") or fragment.get("duration_sec")
        intel = fragment.get("intelligence")
        txt = None
        audio_energy = fragment.get("audio_energy")
        motion_score = fragment.get("motion_score")
        
        # Query database to enrich the fragment data
        db_fetch = SessionLocal()
        try:
            from archive.db_models import FragmentTable, EvidenceTable
            db_frag = db_fetch.query(FragmentTable).filter_by(fragment_id=fid).first()
            if db_frag:
                if duration is None:
                    duration = db_frag.end_time - db_frag.start_time
                if intel is None:
                    intel = db_frag.intelligence or {}
            
            db_ev = db_fetch.query(EvidenceTable).filter_by(fragment_id=fid).first()
            if db_ev:
                if audio_energy is None:
                    audio_energy = db_ev.audio_energy
                if motion_score is None:
                    motion_score = db_ev.motion_score
                if txt is None:
                    txt = (db_ev.text or "").lower()
        except Exception as db_err:
            print(f"[WEAK LABELER][WARN] Failed to enrich fragment {fid} from DB: {db_err}")
        finally:
            db_fetch.close()
            
        # Set defaults if still unresolved
        if duration is None: duration = 5.0
        else: duration = float(duration)
        
        if intel is None: intel = {}
        
        if txt is None:
            txt = str(intel.get("transcript", "") or fragment.get("semantic", {}).get("transcript_refs", "")).lower()
            
        if audio_energy is None:
            audio_energy = float(fragment.get("evidence", {}).get("audio_energy", 0.4))
        else:
            audio_energy = float(audio_energy)
            
        if motion_score is None:
            motion_score = float(fragment.get("evidence", {}).get("motion_score", 0.3))
        else:
            motion_score = float(motion_score)

        weak_labels = []

        # Heuristic 1: Hook Candidate (high motion/audio at start of source)
        if start_time <= 8.0:
            if audio_energy > 0.65 and motion_score > 0.55:
                weak_labels.append({
                    "label_name": "hook_candidate",
                    "confidence": 0.78,
                    "rule_source": "LF_HookCandidate"
                })

        # Heuristic 2: Boredom Risk (long duration, no text, low movement)
        if duration >= 7.5:
            if not txt and motion_score < 0.25:
                weak_labels.append({
                    "label_name": "boredom_risk",
                    "confidence": 0.85,
                    "rule_source": "LF_BoredomRisk"
                })

        # Heuristic 3: Reaction Hold Good (laugh detected with decent hold duration)
        if "하하" in txt or "ㅋㅋㅋ" in txt or "laugh" in txt:
            if role == "reaction" and 1.2 <= duration <= 3.5:
                weak_labels.append({
                    "label_name": "reaction_hold_good",
                    "confidence": 0.75,
                    "rule_source": "LF_ReactionHoldGood"
                })

        # Heuristic 4: Cognitive Overload Risk (hyperactive cut intervals)
        if duration < 1.4 and role == "scenery":
            weak_labels.append({
                "label_name": "cognitive_overload_risk",
                "confidence": 0.65,
                "rule_source": "LF_CognitiveOverload"
            })

        # Heuristic 5: Audio Cut Bad (highly energetic dialogue cut mid-stream)
        if audio_energy > 0.82 and len(txt) > 0:
            # If the fragment is short, it might represent a chopped voice
            if duration < 1.2:
                weak_labels.append({
                    "label_name": "audio_cut_bad",
                    "confidence": 0.68,
                    "rule_source": "LF_AudioCutBad"
                })

        # Save to database
        if weak_labels:
            db = SessionLocal()
            try:
                for wl in weak_labels:
                    existing = db.query(WeakLabelTable).filter_by(
                        fragment_id=fid,
                        label_name=wl["label_name"],
                        rule_source=wl["rule_source"]
                    ).first()
                    if existing:
                        existing.confidence = wl["confidence"]
                        existing.source_id = source_id
                    else:
                        row = WeakLabelTable(
                            fragment_id=fid,
                            source_id=source_id,
                            label_name=wl["label_name"],
                            confidence=wl["confidence"],
                            rule_source=wl["rule_source"]
                        )
                        db.add(row)
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[WEAK LABELER][ERROR] Failed to save weak labels for frag {fid}: {e}")
            finally:
                db.close()

        return weak_labels
