import uuid
import engine.proposal_guards as guards

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
        
        user_intent = self.bams.get_user_intent(source_id)
        if not user_intent:
            quick_scan = self.bams.get_quick_scan(source_id)
            user_intent = quick_scan.get("default_intent_seed") if quick_scan else {}
            
        target_len_raw = user_intent.get("target_length", 60.0) if user_intent else 60.0
        
        proposals = self.generate_proposals_from_fragments(
            project_id=source_id, 
            source_ids=[source_id], 
            fragments=fragments, 
            target_len=target_len_raw,
            story_context={"user_intent": user_intent} # [STEP 10-K-B2] Minimal bridge
        )
        
        # 5. 저장 (generate_proposals_from_fragments는 저장을 수행하지 않으므로 여기서 수행)
        self.bams.save_proposals(source_id, proposals)
        
        print(f"[PROPOSAL ENGINE] generate_proposals EXIT: {source_id}")
        return proposals

    def generate_proposals_from_fragments(self, project_id, source_ids, fragments, target_len=60.0, story_context=None):
        """
        [STEP 10-I.5.24] 여러 소스의 조각 Pool에서 A/B 제안 생성
        """
        print(f"[PROPOSAL ENGINE] generate_proposals_from_fragments ENTER: proj={project_id}, sources={source_ids}")
        
        if not fragments:
            print("[PROPOSAL ENGINE] No fragments provided")
            return []

        # [STEP 10-I.5.19] 진단 로그
        durations = [self._safe_duration(f) for f in fragments]
        none_count = sum(1 for f in fragments if f.get("structural", {}).get("duration") is None)
        zero_count = sum(1 for d in durations if d <= 0)
        print(f"[PROPOSAL ENGINE] Pool Diagnostics - Total: {len(fragments)}, None: {none_count}, Zero: {zero_count}")
        
        target_len = self._safe_target_len(target_len, fragments)
        print(f"[PROPOSAL ENGINE] target_len normalized: {target_len}")

        # 1. Mode A (Market) 생성
        print("[PROPOSAL ENGINE] Creating Market Proposal (A)...")
        p_a = self._create_market_proposal(project_id, fragments, target_len, source_ids)
        
        # 2. Mode B (User) 생성
        print("[PROPOSAL ENGINE] Creating User Proposal (B)...")
        # [STEP 10-I.5.28-E8-R1] A안 선택 ID 추출하여 중복 페널티용으로 전달
        market_selected_ids = {f["fragment_id"] for f in p_a["sequence"]}
        
        # [STEP 10-K-B2] Replaced hardcoded intent with story_context
        intent = story_context.get("user_intent", {"target_length": target_len}) if story_context else {"target_length": target_len}
        p_b = self._create_user_proposal(project_id, fragments, target_len, intent, source_ids, market_selected_ids, story_context=story_context)
        
        # 3. A/B 차별성 보완
        if [f["fragment_id"] for f in p_a["sequence"]] == [f["fragment_id"] for f in p_b["sequence"]]:
            p_a["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
            p_b["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
        
        proposals = [p_a, p_b]

        # [STEP 10-K-C1-R38] Live Proposal Path Proof
        print("[R38_PROPOSAL_ENGINE_LIVE] generate_proposals_from_fragments active")

        def _debug_seq(label, seq):
            print(f"[R38_SEQ_{label}] count={len(seq)}")
            for i, f in enumerate(seq[:20]):
                print(
                    f"[R38_SEQ_{label}] "
                    f"{i+1} fid={f.get('fragment_id')} "
                    f"sid={f.get('source_id')} "
                    f"start={f.get('start', f.get('start_time'))} "
                    f"end={f.get('end', f.get('end_time'))} "
                    f"start_frame={f.get('start_frame')} "
                    f"end_frame={f.get('end_frame')}"
                )

        _debug_seq("BEFORE_A", p_a["sequence"])
        _debug_seq("BEFORE_B", p_b["sequence"])

        # [STEP 10-K-C1-R37] 최종 시퀀스 하드 가드 적용 (어떠한 경우에도 연속 구간 허용 금지)
        p_a["sequence"] = guards.hard_guard_final_sequence(p_a["sequence"])
        p_b["sequence"] = guards.hard_guard_final_sequence(p_b["sequence"])

        _debug_seq("AFTER_A", p_a["sequence"])
        _debug_seq("AFTER_B", p_b["sequence"])

        # 가드 적용 후 최종 duration 재계산
        p_a["duration"] = round(sum(self._safe_duration(f) for f in p_a["sequence"]), 2)
        p_b["duration"] = round(sum(self._safe_duration(f) for f in p_b["sequence"]), 2)

        # [PROPOSAL_BALANCED_SOURCES_AFTER]
        import json
        after_dist = self._calculate_source_distribution(p_b["sequence"])
        print(f"[PROPOSAL_BALANCED_SOURCES_AFTER] selected_count={len(p_b['sequence'])}, source_distribution={json.dumps(after_dist, ensure_ascii=False)}, used_source_count={after_dist['source_count']}, total_duration={p_b['duration']}")

        for p in proposals:
            p["project_id"] = project_id
            p["source_ids"] = source_ids
            p["proposal_explanation"] = self._generate_explanation(
                project_id=project_id,
                source_ids=source_ids,
                fragments_pool=fragments,
                selected_sequence=p["sequence"],
                mode=p["mode"],
                overlap_ids=market_selected_ids if p["mode"] == "B" else None
            )

        print(f"[PROPOSAL ENGINE] generate_proposals_from_fragments EXIT: {project_id}")
        return proposals

    def _create_market_proposal(self, source_id, fragments, target_len, source_ids=None, overlap_ids=None):
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
        source_count = len(source_ids) if source_ids else 1

        # [STEP2C-R2] single-source / multi-source max_frags 분리
        # 기존: min(source_count * 2, 40) → source=1 이면 max_frags=2 고정 문제
        if source_count == 1:
            # 단일 source: fragment 수 기반, 최대 12개
            max_frags = min(len(fragments), 12)
        else:
            # 멀티 source: diversity 보호 유지, 최솟값 6 보장
            _base = source_count * 2 if is_fast_path else source_count * 3
            _cap  = 40 if is_fast_path else 60
            max_frags = min(max(_base, 6), _cap)

        print(f"[PROPOSAL ENGINE][R2] Market max_frags={max_frags} "
              f"source_count={source_count} is_fast_path={is_fast_path} "
              f"fragment_pool={len(fragments)}")

        # [STEP 10-I.5.28-E8-R1] 소스 밸런싱 추적
        source_counts = {}
        is_multi = source_ids and len(source_ids) > 1

        for f in sorted_frags:
            f_dur = self._safe_duration(f)
            f_sid = f.get("source_id")
            
            if len(selected) >= max_frags: break
            
            # [STEP 10-I.5.28-E8-R1] Source Soft Balance (Market: 0.9 penalty)
            if is_multi and len(selected) > 2:
                share = source_counts.get(f_sid, 0) / len(selected)
                max_share = 0.25 if source_count >= 10 else 0.35 if source_count >= 5 else 0.5
                if share > max_share:
                    # 너무 많이 선택된 소스면 일단 건너뛰고 나중에 공간 남으면 채움 (Soft Skip)
                    if current_len + f_dur <= target_len * 0.8: # 여유가 많을 때만 페널티 적용
                         continue

            if current_len + f_dur <= target_len * 1.1:
                # [STEP 10-K-C1-R36] 선택 단계 Guard: 이미 선택된 조각과 연속되는지 확인
                if guards.is_contiguous_to_selected(f, selected):
                    continue
                selected.append(f)
                current_len += f_dur
                source_counts[f_sid] = source_counts.get(f_sid, 0) + 1
        
        print(f"[PROPOSAL ENGINE] Market Proposal (A) - Selected {len(selected)} fragments, total {current_len:.1f}s")
        # [STEP 10-K-C1-R37] Disable Bridge Reinsertion to prevent contiguous fragment leakage
        # selected, bridge_details = self._insert_bridges(selected, fragments)
        bridge_details = []
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

    def _semantic_group_key(self, fragment_id: str) -> str:
        """
        [STEP 2-C-R4] SF_CD37EA_SRC_616AEFBA_P001 → SF_CD37EA_SRC_616AEFBA
        마지막 _P001, _P002 같은 part suffix를 제거해 같은 semantic group으로 묶는다.
        """
        import re
        return re.sub(r'_P\d+$', '', fragment_id or "")

    def _create_user_proposal(self, source_id, fragments, target_len, intent, source_ids=None, overlap_ids=None, story_context=None):
        """B: User Mode (User Intent 엄격 반영 + A안 중복 페널티)"""
        # [STEP 2-C-R4] B-mode Diversity Scoring
        # A안이 이미 선택한 group과 B가 현재 선택한 group을 추적하여 diversity 유도
        a_fragment_ids = overlap_ids if overlap_ids else set()
        a_group_keys = {self._semantic_group_key(fid) for fid in a_fragment_ids}
        selected_b_group_keys = set()

        def edit_score(f):
            base_val = float(f.get("structural", {}).get("edit_value", 0.5))
            group_key = self._semantic_group_key(f.get("fragment_id"))
            
            score = base_val
            
            # Rule 2 & 3: A와 다른 semantic group 우선
            if group_key in a_group_keys:
                score *= 0.25   # A가 이미 쓴 group 강한 감점 (홀짝 분할 방지)
            
            # Rule 1: B 내부 반복 감점
            if group_key in selected_b_group_keys:
                score *= 0.3    # B 내부 반복 감점
            
            # Rule 3: 새로운 group 보너스
            if group_key not in a_group_keys and group_key not in selected_b_group_keys:
                score *= 1.15   # 새로운 group 보너스
                
            return score

        # 정렬 기준: 1. b_score 내림차순, 2. start 오름차순 (결정론 유지)
        sorted_frags = sorted(fragments, key=lambda x: (edit_score(x), -x.get("start", 0)), reverse=True)

        is_balanced_sources = False
        if intent:
            if intent.get("coverage") == "balanced_sources":
                is_balanced_sources = True
            else:
                instruction_text = intent.get("instruction_text", "")
                if instruction_text:
                    lower_text = instruction_text.lower()
                    if "골고루" in lower_text or "balanced" in lower_text or "여러 영상" in lower_text:
                        is_balanced_sources = True

        threshold_used = 0.05 if is_balanced_sources else 0.1

        # [PROPOSAL_BALANCED_SOURCES_INPUT]
        eligible_frags = [f for f in fragments if float(f.get("structural", {}).get("edit_value", 0.5)) >= threshold_used]
        eligible_source_count = len(set(f.get("source_id") for f in eligible_frags if f.get("source_id")))
        import json
        print(f"[PROPOSAL_BALANCED_SOURCES_INPUT] requested_source_count={len(source_ids) if source_ids else 1}, candidate_source_count={len(set(f.get('source_id') for f in fragments if f.get('source_id')))}, eligible_after_threshold={eligible_source_count}, threshold_used={threshold_used}, user_intent={json.dumps(intent, ensure_ascii=False)}")

        # [PROPOSAL_BALANCED_SOURCES_BEFORE]
        before_dist = self._calculate_source_distribution(fragments)
        print(f"[PROPOSAL_BALANCED_SOURCES_BEFORE] source_distribution={json.dumps(before_dist, ensure_ascii=False)}")

        selected = []
        current_len = 0
        source_counts = {}
        _low_edit_excluded = 0

        if is_balanced_sources:
            # 1. source별로 eligible_frags 그룹화
            source_to_frags = {}
            for f in eligible_frags:
                sid = f.get("source_id")
                if sid:
                    if sid not in source_to_frags:
                        source_to_frags[sid] = []
                    source_to_frags[sid].append(f)

            # 2. 각 source 그룹 내부 조각들을 edit_score 기준 내림차순 정렬 (start_time 내림차순 등으로 결정론 유지)
            for sid in source_to_frags:
                source_to_frags[sid] = sorted(source_to_frags[sid], key=lambda x: (edit_score(x), -x.get("start", 0)), reverse=True)

            # 3. 1차 라운드: source별 best candidate 1개씩 우선 선별
            for sid in (source_ids or []):
                frags_for_sid = source_to_frags.get(sid, [])
                if not frags_for_sid:
                    continue
                for f in frags_for_sid:
                    f_dur = self._safe_duration(f)
                    if current_len + f_dur <= target_len * 1.1:
                        if guards.is_contiguous_to_selected(f, selected):
                            continue
                        selected.append(f)
                        f_group_key = self._semantic_group_key(f.get("fragment_id"))
                        selected_b_group_keys.add(f_group_key)
                        current_len += f_dur
                        source_counts[sid] = source_counts.get(sid, 0) + 1
                        break

            # 4. 2차 라운드: target_length 초과 전까지 round-robin 추가
            used_fids = {f.get("fragment_id") for f in selected}
            has_more = True

            # max_frags 계산
            is_fast_path = target_len <= 60.0
            source_count = len(source_ids) if source_ids else 1
            if source_count == 1:
                max_frags = min(len(fragments), 12)
            else:
                _base = source_count * 2 if is_fast_path else source_count * 3
                _cap  = 40 if is_fast_path else 60
                max_frags = min(max(_base, 6), _cap)

            print(f"[PROPOSAL ENGINE][R4] User(Diversity-Balanced) max_frags={max_frags} source_count={source_count} target_len={target_len}")

            while has_more and current_len < target_len and len(selected) < max_frags:
                has_more = False
                for sid in (source_ids or []):
                    if len(selected) >= max_frags:
                        break
                    frags_for_sid = source_to_frags.get(sid, [])
                    if not frags_for_sid:
                        continue

                    next_frag = None
                    for f in frags_for_sid:
                        if f.get("fragment_id") not in used_fids:
                            next_frag = f
                            break

                    if next_frag:
                        has_more = True
                        f_dur = self._safe_duration(next_frag)

                        # 같은 source 과다 점유 제한 (share > 0.55 시 skip)
                        if len(selected) > 2:
                            share = source_counts.get(sid, 0) / len(selected)
                            if share > 0.55:
                                if current_len + f_dur <= target_len * 0.9:
                                    continue

                        if current_len + f_dur <= target_len * 1.1:
                            if guards.is_contiguous_to_selected(next_frag, selected):
                                used_fids.add(next_frag.get("fragment_id"))
                                continue
                            selected.append(next_frag)
                            used_fids.add(next_frag.get("fragment_id"))
                            f_group_key = self._semantic_group_key(next_frag.get("fragment_id"))
                            selected_b_group_keys.add(f_group_key)
                            current_len += f_dur
                            source_counts[sid] = source_counts.get(sid, 0) + 1
                            if current_len >= target_len:
                                break

            # _low_edit_excluded 카운팅
            for f in fragments:
                if f.get("structural", {}).get("edit_value", 0.5) < threshold_used:
                    _low_edit_excluded += 1

        else:
            # 기존 B안 선별 알고리즘 (else 분기로 기존 로직 완전 보존)
            is_fast_path = target_len <= 60.0
            source_count = len(source_ids) if source_ids else 1
            if source_count == 1:
                max_frags = min(len(fragments), 12)
            else:
                _base = source_count * 2 if is_fast_path else source_count * 3
                _cap  = 40 if is_fast_path else 60
                max_frags = min(max(_base, 6), _cap)

            print(f"[PROPOSAL ENGINE][R4] User(Diversity) max_frags={max_frags} "
                  f"source_count={source_count} is_fast_path={is_fast_path} "
                  f"fragment_pool={len(fragments)}")

            is_multi = source_ids and len(source_ids) > 1

            for f in sorted_frags:
                f_group_key = self._semantic_group_key(f.get("fragment_id"))

                # 엄격한 필터링: edit_value가 0.1 미만이면 제외
                if f.get("structural", {}).get("edit_value", 0.5) < 0.1:
                    _low_edit_excluded += 1
                    continue
                f_dur = self._safe_duration(f)
                f_sid = f.get("source_id")

                if len(selected) >= max_frags: break

                # [STEP 10-I.5.28-E8-R1] Source Soft Balance (User: 0.8 penalty)
                if is_multi and len(selected) > 2:
                    share = source_counts.get(f_sid, 0) / len(selected)
                    if share > 0.55: # 유저 모드는 조금 더 유연하게 상향
                        if current_len + f_dur <= target_len * 0.9:
                            continue

                if current_len + f_dur <= target_len * 1.1:
                    if guards.is_contiguous_to_selected(f, selected):
                        continue
                    selected.append(f)
                    selected_b_group_keys.add(f_group_key)
                    current_len += f_dur
                    source_counts[f_sid] = source_counts.get(f_sid, 0) + 1

        # [STEP 2-C-R4-R1] B Exclusive Group Fallback Fix
        b_group_keys = {self._semantic_group_key(f.get("fragment_id")) for f in selected}
        exclusive_groups = b_group_keys - a_group_keys

        if not exclusive_groups and fragments:
            print(f"[PROPOSAL ENGINE][R4-R1] No exclusive groups in B. Attempting fallback from pool (size={len(fragments)})")
            
            # A에 없는 그룹 중 edit_value가 가장 높은 후보 찾기 (전체 pool 대상)
            fallback_candidates = []
            for f in fragments:
                g_key = self._semantic_group_key(f.get("fragment_id"))
                if g_key in a_group_keys:
                    continue
                
                f_struct = f.get("structural") or {}
                f_ev = float(f_struct.get("edit_value", 0.0))
                f_dur = self._safe_duration(f)
                
                if f_ev >= 0.05 and f_dur > 0:
                    fallback_candidates.append(f)
            
            # 정렬: edit_value 내림차순, start 오름차순
            fallback_candidates = sorted(fallback_candidates, key=lambda x: (float(x.get("structural", {}).get("edit_value", 0.0)), -x.get("start", 0)), reverse=True)
            
            if fallback_candidates:
                best_fallback = fallback_candidates[0]
                fb_dur = self._safe_duration(best_fallback)
                fb_id = best_fallback.get("fragment_id")
                
                # 1. duration cap 여유가 있으면 추가 (1.2배까지 허용)
                if current_len + fb_dur <= target_len * 1.2:
                     selected.append(best_fallback)
                     print(f"[PROPOSAL ENGINE][R4-R1] Fallback added unique group fragment: {fb_id} (ev={best_fallback.get('structural', {}).get('edit_value')})")
                # 2. 여유 없으면 가장 낮은 점수 조각과 교체 (B-mode scoring 기준)
                elif selected:
                    weakest_idx = 0
                    min_score = 999.0
                    for i, f in enumerate(selected):
                        # edit_score는 내부함수이므로 접근 가능
                        s = edit_score(f)
                        if s < min_score:
                            min_score = s
                            weakest_idx = i
                    
                    print(f"[PROPOSAL ENGINE][R4-R1] Fallback replacing weakest to ensure diversity: {selected[weakest_idx].get('fragment_id')} -> {fb_id}")
                    selected[weakest_idx] = best_fallback
            else:
                print("[PROPOSAL ENGINE][R4-R1] NO_EXCLUSIVE_GROUP_CANDIDATE: Could not find any fragments outside A's groups with ev >= 0.05")

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
                
                # Confidence 높은 순으로 최대 8개 선택하되, 연속 조각 방지 적용
                fallback_selected = []
                for f in sorted(candidates, key=lambda x: x.get("confidence", 0.5), reverse=True):
                    if guards.is_contiguous_to_selected(f, fallback_selected):
                        continue
                    fallback_selected.append(f)
                    if len(fallback_selected) >= 8:
                        break
                
                # 결과가 너무 적으면 최소 개수 보장 위해 연속성 허용하여 보충
                if len(fallback_selected) < 2:
                    selected = sorted(candidates, key=lambda x: x.get("confidence", 0.5), reverse=True)[:3]
                else:
                    selected = fallback_selected

            # 유저 모드는 원래 순서(연대기순)를 선호하므로 재정렬
            selected = sorted(selected, key=lambda x: x.get("start", 0))
            current_len = sum(self._safe_duration(f) for f in selected)

        print(f"[PROPOSAL ENGINE] User Proposal (B) - Selected {len(selected)} fragments, "
              f"total {current_len:.1f}s, low_edit_excluded={_low_edit_excluded}")
        # [STEP 10-K-C1-R37] Disable Bridge Reinsertion to prevent contiguous fragment leakage
        # selected, bridge_details = self._insert_bridges(selected, fragments)
        bridge_details = []
        
        # [STEP 10-K-B3] Balanced Source Constraint 적용
        balance_info = {"applied": False, "template_id": None, "warnings": []}
        source_dist = self._calculate_source_distribution(selected)
        
        template_id = story_context.get("template_id") if story_context else None
        if template_id == "balanced_multi_source_record":
            hard_constraints = story_context.get("hard_constraints", {})
            constraints = {
                "min_source_coverage_ratio": hard_constraints.get("min_source_coverage_ratio", 0.6),
                "min_fragments_per_selected_source": hard_constraints.get("min_fragments_per_selected_source", 1),
                "max_single_source_clip_ratio": hard_constraints.get("max_single_source_clip_ratio", 0.35)
            }
            selected, b_warnings = self._apply_balanced_source_constraints(selected, fragments, constraints)
            balance_info.update({
                "applied": True,
                "template_id": template_id,
                "warnings": b_warnings
            })
            # 보정 후 분포 재계산
            source_dist = self._calculate_source_distribution(selected)

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
            "fallback_reason": fallback,
            "source_distribution": source_dist,
            "balance_policy": balance_info if balance_info["applied"] else None
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

    # ═══════════════════════════════════════════════════════════════════
    #   [STEP 10-K-B3] Balanced Source Constraint Helpers
    # ═══════════════════════════════════════════════════════════════════

    def _calculate_source_distribution(self, sequence):
        """[STEP 10-K-B3] 소스별 분포 계산"""
        if not sequence:
            return {"source_count": 0, "total_fragments": 0, "by_source": {}, "max_single_source_ratio": 0.0}
        
        counts = {}
        for f in sequence:
            sid = f.get("source_id", "UNKNOWN")
            counts[sid] = counts.get(sid, 0) + 1
            
        total = len(sequence)
        dist = {
            "source_count": len(counts),
            "total_fragments": total,
            "by_source": {},
            "max_single_source_ratio": 0.0
        }
        
        max_ratio = 0.0
        for sid, count in counts.items():
            ratio = count / total
            dist["by_source"][sid] = {
                "count": count,
                "ratio": round(ratio, 3)
            }
            if ratio > max_ratio:
                max_ratio = ratio
        
        dist["max_single_source_ratio"] = round(max_ratio, 3)
        return dist

    def _apply_balanced_source_constraints(self, selected, candidates, hard_constraints):
        """
        [STEP 10-K-B3] Balanced Source Constraint 보정 로직
        """
        warnings = []
        if not selected:
            return selected, warnings
            
        min_coverage = hard_constraints.get("min_source_coverage_ratio", 0.6)
        # min_frags = hard_constraints.get("min_fragments_per_selected_source", 1) # Reserved for more complex logic
        max_ratio_limit = hard_constraints.get("max_single_source_clip_ratio", 0.35)
        
        # 1. 현재 소스 분포 계산
        dist = self._calculate_source_distribution(selected)
        current_sources = set(dist["by_source"].keys())
        
        # 전체 후보 소스 목록
        all_candidate_sources = set(f.get("source_id") for f in candidates if f.get("source_id"))
        target_source_count = max(1, int(len(all_candidate_sources) * min_coverage))
        
        # 2. 부족한 소스 보충 (Coverage 보장)
        if len(current_sources) < target_source_count:
            missing_sources = all_candidate_sources - current_sources
            # 점수 높은 순으로 후보 정렬 (edit_value 기준)
            sorted_candidates = sorted(candidates, key=lambda x: x.get("structural", {}).get("edit_value", 0.0), reverse=True)
            
            for sid in missing_sources:
                if len(current_sources) >= target_source_count:
                    break
                # 해당 소스의 가장 좋은 조각 하나 선택
                for f in sorted_candidates:
                    if f.get("source_id") == sid:
                        selected.append(f)
                        current_sources.add(sid)
                        break
            
            if len(current_sources) < target_source_count:
                warnings.append("insufficient_source_count")

        # 3. Max Ratio 체크 및 보정 (단일 소스의 점유율이 max_ratio_limit를 초과하지 않도록 보장)
        iterations = 0
        max_iterations = 30
        while iterations < max_iterations:
            dist = self._calculate_source_distribution(selected)
            if not selected:
                break
            
            max_sid = None
            max_ratio = 0.0
            for sid, info in dist["by_source"].items():
                if info["ratio"] > max_ratio:
                    max_ratio = info["ratio"]
                    max_sid = sid
            
            if max_ratio <= max_ratio_limit:
                break
            
            over_frags = [f for f in selected if f.get("source_id") == max_sid]
            if not over_frags:
                break
            
            worst_frag = min(over_frags, key=lambda x: x.get("structural", {}).get("edit_value", 0.0))
            selected_ids = {f.get("id") for f in selected}
            potential_replacements = []
            
            for c in candidates:
                if c.get("id") in selected_ids:
                    continue
                c_sid = c.get("source_id")
                if not c_sid or c_sid == max_sid:
                    continue
                
                # 임시 시뮬레이션
                temp_selected = [f for f in selected if f.get("id") != worst_frag.get("id")] + [c]
                temp_dist = self._calculate_source_distribution(temp_selected)
                if temp_dist["max_single_source_ratio"] <= max_ratio_limit or temp_dist["max_single_source_ratio"] < max_ratio:
                    potential_replacements.append(c)
            
            if potential_replacements:
                best_replacement = max(potential_replacements, key=lambda x: x.get("structural", {}).get("edit_value", 0.0))
                selected.remove(worst_frag)
                selected.append(best_replacement)
            else:
                if len(selected) > 2:
                    selected.remove(worst_frag)
                else:
                    warnings.append("max_single_source_clip_ratio_exceeded")
                    break
            
            iterations += 1
            
        if iterations >= max_iterations:
            warnings.append("max_single_source_clip_ratio_adjustment_reached_limit")

        # 4. Source Rotation (간단한 정렬 보정)
        balanced_seq = []
        if selected:
            # 시간순 정렬된 상태에서 시작
            temp_list = sorted(selected, key=lambda x: x.get("start", 0))
            last_sid = None
            while temp_list:
                found = False
                for i, f in enumerate(temp_list):
                    if f.get("source_id") != last_sid:
                        balanced_seq.append(temp_list.pop(i))
                        last_sid = balanced_seq[-1].get("source_id")
                        found = True
                        break
                if not found:
                    balanced_seq.append(temp_list.pop(0))
                    last_sid = balanced_seq[-1].get("source_id")
                    
        return balanced_seq, warnings

    def _generate_story(self, mode, sequence):
        """
        [STEP 4] 편집 스토리 / 시나리오 요약 생성
        [STEP 10-I.5.24] 멀티 소스 감지 및 문구 분기
        """
        source_ids = set(f.get("source_id") for f in sequence if f.get("source_id"))
        is_multi = len(source_ids) > 1

        if mode == "A":
            title = "시장형 편집" if not is_multi else "교차 하이라이트 편집"
            if not is_multi:
                story = (
                    "초반에는 가장 눈에 들어오는 장면으로 시작해 시선을 끕니다. "
                    "이후 움직임이 있는 장면을 이어 붙여 영상의 리듬을 빠르게 만들고, "
                    "중복되는 구간은 줄여 짧고 선명한 흐름으로 정리합니다. "
                    "마지막은 안정적인 장면으로 마무리해 전체 인상을 깔끔하게 남깁니다."
                )
                keywords = ["초반 몰입", "빠른 전개", "반복 최소화", "짧은 완성도"]
            else:
                story = (
                    "서로 다른 영상에서 눈에 잘 들어오는 장면을 골라 빠르게 이어 붙집니다. "
                    "초반에는 가장 선명한 장면으로 시선을 잡고, "
                    "중간에는 분위기가 다른 장면을 교차시켜 변화감을 만듭니다. "
                    "마지막은 가장 안정적인 장면으로 정리해 짧은 모음 영상처럼 마무리합니다."
                )
                keywords = ["여러 영상 하이라이트", "빠른 전개", "장면 대비", "짧은 완성도"]
        else:
            title = "사용자친화형 편집" if not is_multi else "흐름 통합 편집"
            if not is_multi:
                story = (
                    "처음에는 원본의 분위기를 자연스럽게 보여주며 시작합니다. "
                    "장면의 시간 흐름을 크게 흔들지 않고 이어가며, "
                    "사용자가 촬영한 현장의 느낌을 유지합니다. "
                    "중복되는 부분만 가볍게 줄이고 자연스럽게 마무리합니다."
                )
                keywords = ["원본 흐름 유지", "자연스러운 전개", "기록성", "편안한 감상"]
            else:
                story = (
                    "각 영상의 분위기를 크게 섞지 않고, 장면들을 차례로 보여줍니다. "
                    "서로 다른 장소나 상황은 구간별로 나누어 배치하고, "
                    "중복되는 부분은 줄이되 원본의 흐름은 유지합니다. "
                    "전체적으로 하루 기록을 요약한 영상처럼 자연스럽게 정리합니다."
                )
                keywords = ["원본 흐름 유지", "여러 장면 정리", "기록성", "편안한 감상"]

        return {
            "title": title,
            "story_summary": story,
            "intent_keywords": keywords,
            "hidden_fragment_refs": [f.get("fragment_id") for f in sequence]
        }

    # ═══════════════════════════════════════════════════════════════════
    #   [STEP 10-I.5.25] Explanation & Storyline Trace Logic
    # ═══════════════════════════════════════════════════════════════════

    def _generate_explanation(self, project_id, source_ids, fragments_pool, selected_sequence, mode, overlap_ids=None):
        """사람이 읽을 수 있는 제안 근거 및 스토리라인 추적 생성"""
        
        is_multi = len(source_ids) > 1
        mode_label = "시장형(Market)" if mode == "A" else "사용자친화형(User)"
        
        # 1. Project Summary
        summary = (
            f"이 프로젝트는 {len(source_ids)}개의 소스 영상을 분석하여 "
            f"{mode_label} 관점으로 최적의 {len(selected_sequence)}개 장면을 선정했습니다. "
            f"멀티 소스 환경에서 {'교차 편집' if is_multi else '단일 흐름'}을 최우선으로 고려했습니다."
        )

        # 2. Source Summaries (전체 분석 조각 vs 제안 사용 조각 구분)
        source_summaries = self._summarize_sources(source_ids, fragments_pool, selected_sequence)

        # 3. Storyline Trace
        storyline = self._trace_storyline(selected_sequence)

        # 4. Selection Reasons
        selection_reasons = self._build_selection_reasons(selected_sequence, mode)

        # 5. Quality Warnings (다양성 알림 추가)
        quality_warnings = self._detect_quality_warnings(source_ids, fragments_pool, selected_sequence)
        if mode == "B" and overlap_ids:
             quality_warnings.append("A안과의 차별화를 위해 일부 중복 조각의 우선순위를 조정했습니다.")

        return {
            "project_summary": summary,
            "source_summaries": source_summaries,
            "storyline": storyline,
            "selection_reasons": selection_reasons,
            "exclusion_policy": [
                "비슷한 구도나 중복되는 장면군은 다양성을 위해 제외 시도",
                "지나치게 짧거나 분석 신뢰도가 낮은 조각은 후순위 배치",
                "특정 영상에 편중되지 않도록 소스 균형 보정 적용 (R1)"
            ],
            "quality_warnings": quality_warnings
        }

    def _summarize_sources(self, source_ids, fragments_pool, selected_sequence=None):
        summaries = []
        # [STEP 10-I.5.27-E6-R1] Expand labels to full A-Z for safety
        labels = [chr(i) for i in range(ord('A'), ord('Z') + 1)] 
        
        # [STEP 10-I.5.27-E6] Stable Dedupe & Labeling Normalize
        clean_source_ids = []
        seen_ids = set()
        for sid in source_ids:
            if sid and sid not in seen_ids:
                clean_source_ids.append(sid)
                seen_ids.add(sid)

        for i, sid in enumerate(clean_source_ids):
            src_frags = [f for f in fragments_pool if f.get("source_id") == sid]
            if not src_frags: continue
            
            # [STEP 10-I.5.27-E6] 제안 사용 조각 수 계산
            proposed_count = 0
            if selected_sequence:
                proposed_count = sum(1 for f in selected_sequence if f.get("source_id") == sid)

            # Dominant Topic & Visual Character
            topics = [f.get("semantic", {}).get("topic", "general") for f in src_frags]
            dom_topic = max(set(topics), key=topics.count) if topics else "unknown"
            if dom_topic == "general": dom_topic = "구체 주제 미확정"
            
            # Visual character (simplified)
            roles = [f.get("structural", {}).get("role", "main") for f in src_frags]
            has_hook = "hook" in roles
            visual_char = "시각적 임팩트(Hook) 포함" if has_hook else "안정적인 흐름 위주"
            
            # Audio status
            has_transcript = any(f.get("semantic", {}).get("transcript_refs") for f in src_frags)
            audio_status = "available" if has_transcript else "missing"

            summaries.append({
                "source_id": sid,
                "source_label": labels[i] if i < len(labels) else f"S{i+1}",
                "summary": f"{len(src_frags)}개의 장면 조각이 분석되었습니다.",
                "dominant_topic": dom_topic,
                "visual_character": visual_char,
                "audio_text_status": audio_status,
                "fragment_count": len(src_frags),
                "proposed_count": proposed_count # [STEP 10-I.5.27-E6] 추가
            })
        return summaries

    def _trace_storyline(self, sequence):
        if not sequence: return []
        
        trace = []
        count = len(sequence)
        
        # 1. Opening
        trace.append({
            "step": 1,
            "role": "opening",
            "description": "가장 시선을 끄는 장면으로 도입부를 구성합니다.",
            "fragment_refs": [sequence[0].get("fragment_id")]
        })
        
        # 2. Main/Development
        if count > 2:
            mid_idx = count // 2
            mid_frags = sequence[1:-1]
            # 최대 3개만 표시
            refs = [f.get("fragment_id") for f in mid_frags[:3]]
            
            # 소스 전환 확인
            sources = set(f.get("source_id") for f in sequence)
            desc = "전체적인 흐름을 이어가며 주요 내용을 전달합니다."
            if len(sources) > 1:
                desc += " 소스 간 교차 편집을 통해 변화를 주었습니다."

            trace.append({
                "step": 2,
                "role": "main",
                "description": desc,
                "fragment_refs": refs
            })
            
        # 3. Closing
        trace.append({
            "step": 3,
            "role": "closing",
            "description": "안정적이고 여운이 남는 장면으로 마무리합니다.",
            "fragment_refs": [sequence[-1].get("fragment_id")]
        })
        
        return trace

    def _build_selection_reasons(self, sequence, mode):
        reasons = []
        for i, f in enumerate(sequence):
            role = f.get("structural", {}).get("role", "main")
            market_val = f.get("structural", {}).get("market_value", 0.5)
            edit_val = f.get("structural", {}).get("edit_value", 0.5)
            
            reason = "영상 흐름상 적절한 장면으로 판단"
            if i == 0:
                reason = "도입부 주목도를 높이기 위해 선정" if role == "hook" else "자연스러운 시작을 위해 선정"
            elif i == len(sequence) - 1:
                reason = "깔끔한 마무리를 위해 선정"
            elif role == "hook":
                reason = "중간 몰입도를 유지하는 하이라이트 장면"
            elif mode == "A" and market_val > 0.7:
                reason = "대중적 선호도가 높은 시각적 구성"
            elif mode == "B" and edit_val > 0.7:
                reason = "사용자의 편집 의도와 일치하는 맥락"

            reasons.append({
                "fragment_id": f.get("fragment_id"),
                "source_id": f.get("source_id"),
                "reason": reason,
                "role": role,
                "score_basis": {
                    "market_value": round(float(market_val), 2),
                    "edit_value": round(float(edit_val), 2),
                    "confidence": round(float(f.get("confidence", 0.5)), 2)
                }
            })
        return reasons

    def _detect_quality_warnings(self, source_ids, fragments_pool, selected_sequence):
        warnings = []
        
        # 1. Transcript check
        has_any_transcript = any(f.get("semantic", {}).get("transcript_refs") for f in fragments_pool)
        if not has_any_transcript:
            warnings.append("음성 분석 데이터(Transcript)가 없어 시각 정보 위주로 편집되었습니다.")
            
        # 2. Generic summary check
        summaries = [f.get("semantic", {}).get("summary", "") for f in fragments_pool]
        generic_count = sum(1 for s in summaries if "Visual/Audio Context" in s)
        if len(fragments_pool) > 0 and (generic_count / len(fragments_pool)) > 0.5:
            warnings.append("의미 분석 결과가 일반적(Generic)인 조각이 많아 정밀한 주제 선별이 제한되었습니다.")
            
        # 3. Source diversity check
        if len(source_ids) > 1:
            selected_sources = set(f.get("source_id") for f in selected_sequence)
            if len(selected_sources) == 1:
                warnings.append("멀티 소스 입력이나, 실제 선택된 장면은 단일 소스에 집중되어 있습니다.")
                
        # 4. Thumbnail repetition
        thumbs = [f.get("thumbnail", {}).get("thumbnail_url") for f in selected_sequence if f.get("thumbnail")]
        if len(thumbs) != len(set(thumbs)):
            warnings.append("비슷한 구간이 중복 선택되었을 가능성이 있습니다. (썸네일 중복)")

        return warnings

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
