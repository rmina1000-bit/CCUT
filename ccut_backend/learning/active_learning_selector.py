class ActiveLearningSelector:
    """
    [STEP 14-F] ActiveLearningSelector
    Identifies high-entropy edit sequences and high-drift clips to query for user feedback.
    Helps maximize learning value while minimizing user labeling fatigue.
    """

    @staticmethod
    def should_trigger_active_question(prop_a: dict, prop_b: dict) -> bool:
        """
        Returns True if the ranking engine is highly uncertain about the A/B preference difference.
        """
        score_a = prop_a.get("rerank_score", 0.5)
        score_b = prop_b.get("rerank_score", 0.5)
        
        diff = abs(score_a - score_b)
        
        # Uncertainty trigger: if rerank scores are extremely close (diff <= 0.04)
        if diff <= 0.04:
            print(f"[ACTIVE LEARNING] High uncertainty detected (diff={diff:.4f}). Triggering feedback query.")
            return True
            
        return False

    @staticmethod
    def select_consultation_candidates(sequence: list, anomalies: dict) -> list:
        """
        Selects a list of problematic or interesting fragment IDs that could be highlighted to the user.
        """
        candidates = []
        
        # 1. Inspect cognitive confusion points
        cog_points = anomalies.get("cognitive_confusion_points") or []
        for p in cog_points[:2]:
            fid = p.get("fragment_id")
            if fid and fid not in candidates:
                candidates.append(fid)
                
        # 2. Inspect focus drop points (attention drifts)
        focus_points = anomalies.get("focus_drop_points") or []
        for p in focus_points[:2]:
            fid = p.get("fragment_id")
            if fid and fid not in candidates:
                candidates.append(fid)
                
        # Fallback to reaction/scenery boundaries if no anomalies found
        if not candidates and sequence:
            for f in sequence:
                role = f.get("structural", {}).get("role")
                if role in ["scenery", "reaction"]:
                    candidates.append(f.get("fragment_id"))
                    if len(candidates) >= 2:
                        break
                        
        print(f"[ACTIVE LEARNING] Selected feedback candidates: {candidates}")
        return candidates
