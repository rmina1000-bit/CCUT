import uuid

class ProposalEngine:
    """
    [STEP 6] Proposal Engine (v3.2.1)
    Semantic Fragments를 조합하여 A(Market)/B(User) 두 가지 버전의 제안을 생성합니다.
    """
    def __init__(self, bams):
        self.bams = bams

    def generate_proposals(self, source_id: str):
        print(f"[PROPOSAL ENGINE] generate_proposals ENTER: {source_id}")
        # 1. 필요 데이터 로드
        fragments = self.bams.get_semantic_fragments(source_id)
        if not fragments:
            print(f"[PROPOSAL ENGINE] No fragments for {source_id}")
            return []
        
        print(f"[PROPOSAL ENGINE] Input semantic fragment count: {len(fragments)}")
        
        user_intent = self.bams.get_user_intent(source_id)
        if not user_intent:
            quick_scan = self.bams.get_quick_scan(source_id)
            user_intent = quick_scan.get("default_intent_seed") if quick_scan else {}
            
        target_len = user_intent.get("target_length", 60.0) if user_intent else 60.0

        # 2. Mode A (Market) 생성
        print("[PROPOSAL ENGINE] Creating Market Proposal (A)...")
        p_a = self._create_market_proposal(source_id, fragments, target_len)
        
        # 3. Mode B (User) 생성
        print("[PROPOSAL ENGINE] Creating User Proposal (B)...")
        p_b = self._create_user_proposal(source_id, fragments, target_len, user_intent)
        
        # 4. A/B 차별성 및 정합성 보완 (v3.2.1) - JSON 구조 반영
        if [f["fragment_id"] for f in p_a["sequence"]] == [f["fragment_id"] for f in p_b["sequence"]]:
            p_a["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
            p_b["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
        
        proposals = [p_a, p_b]
        
        # 5. 저장 및 반환
        self.bams.save_proposals(source_id, proposals)
        
        print(f"[PROPOSAL ENGINE] generate_proposals EXIT: {source_id}")
        return proposals

    def _create_market_proposal(self, source_id, fragments, target_len):
        """A: Market Mode (대중적 호속력)"""
        def market_score(f):
            score = f["structural"].get("market_value", 0.5)
            if f["structural"].get("role") in ["hook", "payoff"]:
                score += 0.1 
            return score

        sorted_frags = sorted(fragments, key=market_score, reverse=True)
        
        selected = []
        current_len = 0
        is_fast_path = target_len <= 60.0
        max_frags = 12 if is_fast_path else 25

        for f in sorted_frags:
            f_dur = f.get("structural", {}).get("duration", 0)
            if f_dur is None:
                print(f"[PROPOSAL ENGINE] Warning: Fragment {f.get('fragment_id')} has null duration")
                f_dur = 0
            
            if len(selected) >= max_frags: break
            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur
        
        print(f"[PROPOSAL ENGINE] Market Proposal (A) - Selected {len(selected)} fragments, total {current_len:.1f}s")
        selected, bridge_details = self._insert_bridges(selected, fragments)
        current_len = sum(f["structural"]["duration"] for f in selected)
        
        # target_length ±10% 정합성
        fallback = None
        status = "within_range"
        if abs(current_len - target_len) > (target_len * 0.1):
             fallback = "significant_length_mismatch"
             status = "out_of_range"
             
        reason_data = {
            "mode_reason": "market_value_and_role_priority",
            "target_length": {
                "target": round(target_len, 2),
                "actual": round(current_len, 2),
                "status": status
            },
            "sequence_reason": "optimized_market_flow",
            "bridge": bridge_details if bridge_details else None
        }

        return {
            "proposal_id": f"PROP_A_{uuid.uuid4().hex[:6].upper()}_{source_id}",
            "source_id": source_id,
            "mode": "A",
            "sequence": selected,
            "duration": round(current_len, 2),
            "proposal_reason": reason_data,
            "confidence": 0.9,
            "fallback_reason": fallback
        }

    def _create_user_proposal(self, source_id, fragments, target_len, intent):
        """B: User Mode (User Intent 엄격 반영)"""
        sorted_frags = sorted(fragments, key=lambda x: x["structural"]["edit_value"], reverse=True)
        
        selected = []
        current_len = 0
        is_fast_path = target_len <= 60.0
        max_frags = 12 if is_fast_path else 25

        for f in sorted_frags:
            if f.get("structural", {}).get("edit_value", 0.5) < 0.1: continue 
            f_dur = f.get("structural", {}).get("duration", 0)
            if f_dur is None:
                print(f"[PROPOSAL ENGINE] Warning: Fragment {f.get('fragment_id')} has null duration")
                f_dur = 0

            if len(selected) >= max_frags: break
            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur

        print(f"[PROPOSAL ENGINE] User Proposal (B) - Selected {len(selected)} fragments, total {current_len:.1f}s")
        selected, bridge_details = self._insert_bridges(selected, fragments)
        current_len = sum(f["structural"]["duration"] for f in selected)
        
        fallback = None
        status = "within_range"
        if abs(current_len - target_len) > (target_len * 0.1):
             fallback = "significant_length_mismatch"
             status = "out_of_range"

        reason_data = {
            "mode_reason": "strict_intent_matching",
            "target_length": {
                "target": round(target_len, 2),
                "actual": round(current_len, 2),
                "status": status
            },
            "sequence_reason": "user_intent_alignment",
            "bridge": bridge_details if bridge_details else None
        }

        return {
            "proposal_id": f"PROP_B_{uuid.uuid4().hex[:6].upper()}_{source_id}",
            "source_id": source_id,
            "mode": "B",
            "sequence": selected,
            "duration": round(current_len, 2),
            "proposal_reason": reason_data,
            "confidence": 0.85,
            "fallback_reason": fallback
        }

    def _insert_bridges(self, selected, all_fragments):
        """
        [STEP 6] Bridge Fragment 예외 추가 및 로그 기록
        """
        print(f"[PROPOSAL ENGINE] _insert_bridges ENTER: input={len(selected)}")
        if len(selected) < 2:
            print("[PROPOSAL ENGINE] _insert_bridges EXIT: too few fragments")
            return selected, []
        
        selected = sorted(selected, key=lambda x: x.get("start", 0))
        augmented = []
        bridge_details = []
        
        for i in range(len(selected) - 1):
            curr = selected[i]
            nxt = selected[i+1]
            augmented.append(curr)
            
            for f in all_fragments:
                if curr["end"] <= f["start"] and f["end"] <= nxt["start"]:
                    # bridge 조건 충족 여부
                    duration = f["structural"]["duration"]
                    continuity = f["continuity"].get("time_proximity", 0.75) # Placeholder default if missing
                    
                    if duration < 5.0 and continuity > 0.7:
                        augmented.append(f)
                        bridge_details.append({
                            "fragment_id": f["fragment_id"],
                            "reason": "continuity_bridge",
                            "continuity": round(continuity, 2),
                            "duration": round(duration, 2)
                        })
                        
        augmented.append(selected[-1])
        
        res = []
        seen = set()
        for f in augmented:
            fid = f.get("fragment_id")
            if fid and fid not in seen:
                res.append(f)
                seen.add(fid)
        
        print(f"[PROPOSAL ENGINE] _insert_bridges EXIT: final={len(res)}, bridges={len(bridge_details)}")
        return res, bridge_details
