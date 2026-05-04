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
        p_b = self._create_user_proposal(project_id, fragments, target_len, intent, source_ids, market_selected_ids)
        
        # 3. A/B 차별성 보완
        if [f["fragment_id"] for f in p_a["sequence"]] == [f["fragment_id"] for f in p_b["sequence"]]:
            p_a["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
            p_b["proposal_reason"]["sequence_reason"] = "same_sequence_due_to_limited_fragments"
        
        proposals = [p_a, p_b]
        
        # 4. Explanation & Storyline Trace 추가 (STEP 10-I.5.25)
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
        max_frags = 12 if is_fast_path else 25

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
                if share > 0.5:
                    # 너무 많이 선택된 소스면 일단 건너뛰고 나중에 공간 남으면 채움 (Soft Skip)
                    if current_len + f_dur <= target_len * 0.8: # 여유가 많을 때만 페널티 적용
                         continue

            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur
                source_counts[f_sid] = source_counts.get(f_sid, 0) + 1
        
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

    def _create_user_proposal(self, source_id, fragments, target_len, intent, source_ids=None, overlap_ids=None):
        """B: User Mode (User Intent 엄격 반영 + A안 중복 페널티)"""
        target_len = self._safe_target_len(target_len, fragments)
        
        # [STEP 10-I.5.28-E8-R1] A안 중복 및 소스 밸런싱 반영 스코어링
        def edit_score(f):
            base = float(f.get("structural", {}).get("edit_value", 0.5))
            # A안 중복 페널티 (soft: 0.7배)
            if overlap_ids and f.get("fragment_id") in overlap_ids:
                base *= 0.7
            return base

        sorted_frags = sorted(fragments, key=edit_score, reverse=True)
        
        selected = []
        current_len = 0
        is_fast_path = target_len <= 60.0
        max_frags = 12 if is_fast_path else 25

        # [STEP 10-I.5.28-E8-R1] 소스 밸런싱 추적
        source_counts = {}
        is_multi = source_ids and len(source_ids) > 1

        for f in sorted_frags:
            # 엄격한 필터링: edit_value가 0.1 미만이면 제외
            if f.get("structural", {}).get("edit_value", 0.5) < 0.1: continue 
            f_dur = self._safe_duration(f)
            f_sid = f.get("source_id")

            if len(selected) >= max_frags: break

            # [STEP 10-I.5.28-E8-R1] Source Soft Balance (User: 0.8 penalty)
            if is_multi and len(selected) > 2:
                share = source_counts.get(f_sid, 0) / len(selected)
                if share > 0.4: # 유저 모드는 조금 더 엄격하게 분산 시도
                    if current_len + f_dur <= target_len * 0.9:
                        continue

            if current_len + f_dur <= target_len * 1.1:
                selected.append(f)
                current_len += f_dur
                source_counts[f_sid] = source_counts.get(f_sid, 0) + 1

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
