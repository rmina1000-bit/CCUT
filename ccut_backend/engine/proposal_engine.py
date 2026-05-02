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
        
        # [STEP 10-I.5.19] 진단 로그
        durations = [self._safe_duration(f) for f in fragments]
        none_count = sum(1 for f in fragments if f.get("structural", {}).get("duration") is None)
        zero_count = sum(1 for d in durations if d <= 0)
        print(f"[PROPOSAL ENGINE] Duration Diagnostics - None: {none_count}, Zero: {zero_count}")
        print(f"[PROPOSAL ENGINE] First 20 durations: {durations[:20]}")
        
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
            f_dur = self._safe_duration(f)
            
            if len(selected) >= max_frags: break
            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur
        
        print(f"[PROPOSAL ENGINE] Market Proposal (A) - Selected {len(selected)} fragments, total {current_len:.1f}s")
        selected, bridge_details = self._insert_bridges(selected, fragments)
        current_len = sum(self._safe_duration(f) for f in selected)
        
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
        # edit_value가 높은 순으로 정렬하여 선택 시도
        def edit_score(f):
            val = f.get("structural", {}).get("edit_value")
            return float(val) if val is not None else 0.5
        sorted_frags = sorted(fragments, key=edit_score, reverse=True)
        
        selected = []
        current_len = 0
        is_fast_path = target_len <= 60.0
        max_frags = 12 if is_fast_path else 25

        for f in sorted_frags:
            # 엄격한 필터링: edit_value가 0.1 미만이면 제외
            if f.get("structural", {}).get("edit_value", 0.5) < 0.1: continue 
            f_dur = self._safe_duration(f)

            if len(selected) >= max_frags: break
            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur

        # [STEP 10-I.5.17] Fallback: Intent 매칭 결과가 비어있을 경우 구제 로직
        fallback = None
        mode_reason = "strict_intent_matching"
        
        if not selected:
            print("[PROPOSAL ENGINE] User Proposal (B) - Intent matching returned empty. Using fallback.")
            fallback = "user_mode_semantic_order_fallback"
            mode_reason = "semantic_order_fallback"
            
            # 최소 3개 또는 전체가 5개 이하이면 전부 사용
            if len(fragments) <= 5:
                selected = fragments
            else:
            # 3초 이상 + confidence 높은 순으로 상위 N개 추출
                candidates = [f for f in fragments if self._safe_duration(f) >= 3.0]
                if len(candidates) < 3:
                    candidates = fragments # 3초 미만이 많으면 전체에서 선택
                
                # Confidence 높은 순으로 최대 8개
                selected = sorted(candidates, key=lambda x: x.get("confidence", 0.5), reverse=True)[:8]
                
            # 유저 모드는 원래 순서(연대기순)를 선호하므로 재정렬
            selected = sorted(selected, key=lambda x: x.get("start", 0))
            current_len = sum(self._safe_duration(f) for f in selected)

        print(f"[PROPOSAL ENGINE] User Proposal (B) - Selected {len(selected)} fragments, total {current_len:.1f}s")
        selected, bridge_details = self._insert_bridges(selected, fragments)
        current_len = sum(self._safe_duration(f) for f in selected)
        
        status = "within_range"
        if not fallback: # fallback이 이미 설정된 경우(비어있음 구제)는 length mismatch 체크보다 우선함
            if abs(current_len - target_len) > (target_len * 0.1):
                fallback = "significant_length_mismatch"
                status = "out_of_range"

        reason_data = {
            "mode_reason": mode_reason,
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
                    duration = self._safe_duration(f)
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

    def _safe_duration(self, frag):
        """[STEP 10-I.5.19] 안전하게 duration 산출 (NoneType crash 방지)"""
        structural = frag.get("structural") or {}
        duration = (
            frag.get("duration_sec")
            or frag.get("duration")
            or structural.get("duration")
        )
        
        # 0.0을 false로 취급하지 않도록 explicit None check가 좋지만, 
        # 위 체인은 duration이 0일 때 아래 start/end 로직을 탈 수 있음.
        # 하지만 start/end 로직도 duration 0을 산출하므로 결과적으로 안전함.
        
        if duration is None:
            # start/end 기반 계산 시도
            start = frag.get("start_sec")
            if start is None: start = frag.get("start")
            if start is None: start = frag.get("start_time")

            end = frag.get("end_sec")
            if end is None: end = frag.get("end")
            if end is None: end = frag.get("end_time")

            if start is not None and end is not None:
                try:
                    duration = float(end) - float(start)
                except:
                    duration = 0.0
        
        try:
            if duration is not None:
                duration = float(duration)
            else:
                duration = 0.0
        except:
            duration = 0.0

        if duration < 0:
            duration = 0.0

        return duration
