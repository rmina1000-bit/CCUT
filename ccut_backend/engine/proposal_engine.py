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
            
        target_len_raw = user_intent.get("target_length", 60.0) if user_intent else 60.0
        target_len = self._safe_target_len(target_len_raw, fragments)
        print(f"[PROPOSAL ENGINE] target_len raw: {target_len_raw}, normalized: {target_len}")

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
        target_len = self._safe_target_len(target_len, fragments)
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

        story_data = self._generate_story("A", selected)
        story_data["proposal_id"] = f"PROP_A_{uuid.uuid4().hex[:6].upper()}_{source_id}"
        story_data["mode"] = "A"

        return {
            "proposal_id": story_data["proposal_id"],
            "source_id": source_id,
            "mode": "A",
            "sequence": selected,
            "duration": round(current_len, 2),
            "proposal_reason": reason_data,
            "proposal_story": story_data,
            "confidence": 0.9,
            "fallback_reason": fallback
        }

    def _create_user_proposal(self, source_id, fragments, target_len, intent):
        """B: User Mode (User Intent 엄격 반영)"""
        target_len = self._safe_target_len(target_len, fragments)
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

        story_data = self._generate_story("B", selected)
        story_data["proposal_id"] = f"PROP_B_{uuid.uuid4().hex[:6].upper()}_{source_id}"
        story_data["mode"] = "B"

        return {
            "proposal_id": story_data["proposal_id"],
            "source_id": source_id,
            "mode": "B",
            "sequence": selected,
            "duration": round(current_len, 2),
            "proposal_reason": reason_data,
            "proposal_story": story_data,
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

    def _generate_story(self, mode, sequence):
        """
        [STEP 4] 편집 스토리 / 시나리오 요약 생성
        """
        if mode == "A":
            title = "시장형 편집"
            story = (
                "초반에는 가장 눈에 들어오는 장면으로 시작해 시선을 끕니다. "
                "이후 움직임이 있는 장면을 이어 붙여 영상의 리듬을 빠르게 만들고, "
                "중복되는 구간은 줄여 짧고 선명한 흐름으로 정리합니다. "
                "마지막은 안정적인 장면으로 마무리해 전체 인상을 깔끔하게 남깁니다."
            )
            keywords = ["초반 몰입", "빠른 전개", "반복 최소화", "짧은 완성도"]
        else:
            title = "사용자친화형 편집"
            story = (
                "처음에는 원본의 분위기를 자연스럽게 보여주며 시작합니다. "
                "장면의 시간 흐름을 크게 흔들지 않고 이어가며, "
                "사용자가 촬영한 현장의 느낌을 유지합니다. "
                "중복되는 부분만 가볍게 줄이고 자연스럽게 마무리합니다."
            )
            keywords = ["원본 흐름 유지", "자연스러운 전개", "기록성", "편안한 감상"]

        return {
            "title": title,
            "story_summary": story,
            "intent_keywords": keywords,
            "hidden_fragment_refs": [f.get("fragment_id") for f in sequence]
        }

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

    def _safe_target_len(self, target_len, fragments):
        """[STEP 10-I.5.20] target_len 안전하게 산출 (NoneType crash 방지)"""
        try:
            if target_len is not None:
                target_len = float(target_len)
        except Exception:
            target_len = None

        if target_len is None or target_len <= 0:
            # fragments 전체 합산의 min(total, 60.0)을 기본값으로 사용
            total = sum(self._safe_duration(f) for f in fragments)
            if total > 0:
                target_len = min(total, 60.0)
            else:
                target_len = 60.0

        return target_len
