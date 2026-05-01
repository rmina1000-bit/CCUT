import datetime
import math
import uuid

class SemanticFragmentGenerator:
    """
    [STEP 4] Semantic Fragment Generator (v3.2.1)
    Evidence Board를 의미 단위(Semantic)로 그룹화하고 Role/Value/Continuity를 부여합니다.
    """
    def __init__(self, bams):
        self.bams = bams

    def generate(self, source_id: str):
        # 1. Evidence 조회
        evidences = self.bams.get_evidence_board(source_id)
        if not evidences:
            print(f"[SEMANTIC] No evidence found for {source_id}")
            return []

        # 2. Quick Scan / default_intent_seed 조회
        quick_scan = self.bams.get_quick_scan(source_id)
        intent_seed = quick_scan.get("default_intent_seed") if quick_scan else self._get_default_intent()
        
        source = self.bams.get_source(source_id)
        total_duration = source.duration if (source and source.duration) else (evidences[-1]["end"] if evidences else 0)

        # 3. 경계 후보 생성 (Evidence-driven: scene, silence, motion, topic)
        boundaries = self.create_fragment_boundaries(evidences)
        
        # 4. Fragment 초기 구축 (Evidence grouping)
        fragments = self.build_fragments(source_id, evidences, boundaries)

        # 5~7. Role, Edit Value, Continuity 계산
        final_fragments = []
        default_intent = self._get_default_intent()
        for frag in fragments:
            # market_value 계산 (고정된 대중적 가치)
            frag["structural"]["market_value"] = self.calculate_edit_value(frag["semantic"]["evidence_refs"], evidences, default_intent)
            
            # edit_value 계산 (종합 근거 반영 - 초기에는 intent_seed 적용)
            frag["structural"]["edit_value"] = self.calculate_edit_value(frag["semantic"]["evidence_refs"], evidences, intent_seed)
            
            # role 분류
            frag["structural"]["role"] = self.classify_role(frag, total_duration, intent_seed)
            
            # continuity 계산
            prev_frag = final_fragments[-1] if final_fragments else None
            frag["continuity"] = self.calculate_continuity(frag, prev_frag)
            
            # confidence & fallback_reason
            frag["confidence"] = self.calculate_confidence(frag)
            frag["fallback_reason"] = self.calculate_fallback_reason(frag)
            
            final_fragments.append(frag)

        # 8. Merge / Split 보정 (2s ~ 60s)
        final_fragments = self.apply_merge_split(final_fragments, boundaries, total_duration)

        # [STEP 4 RESYNC] 최종 경계 확정 후 fallback_reason 재계산
        for frag in final_fragments:
            frag["fallback_reason"] = self.calculate_fallback_reason(frag)

        # 9. DB 저장
        self.bams.save_semantic_fragments(source_id, final_fragments)
        
        print(f"[SEMANTIC] {len(final_fragments)} fragments generated for {source_id}")
        return final_fragments

    def create_fragment_boundaries(self, evidences):
        """
        [STEP 4] 경계 후보 생성 (v3.2.1 보완)
        - scene_change: 리스트 내 모든 지점 반영
        - silence: audio_energy < 0.05
        - motion_score: 급격한 변화 (> 0.4)
        - text_shift: 텍스트 유무 변화 (토픽 전환 힌트)
        """
        boundaries = []
        for i, ev in enumerate(evidences):
            # 1. 원본 세그먼트 경계
            boundaries.append(ev["start"])
            boundaries.append(ev["end"])

            # 2. 씬 체인지 (타임스탬프 리스트)
            if ev.get("scene_change") and isinstance(ev["scene_change"], list):
                for ts in ev["scene_change"]:
                    boundaries.append(ts)
            
            # 3. 침묵 구간 (오디오 에너지 저하)
            if ev.get("audio_energy", 1.0) < 0.05:
                boundaries.append(ev["start"])
            
            # 4. 신호 변화 감지
            if i > 0:
                prev = evidences[i-1]
                # 모션 급변
                if abs(ev.get("motion_score", 0.0) - prev.get("motion_score", 0.0)) > 0.4:
                    boundaries.append(ev["start"])
                # 텍스트 존재 유무 변화
                if bool(ev.get("text")) != bool(prev.get("text")):
                    boundaries.append(ev["start"])
                    
        # [STEP 10-I.3] 중복 및 너무 가까운 경계 제거 (최소 1초 간격 권장)
        sorted_b = sorted(list(set(boundaries)))
        if not sorted_b: return []
        
        filtered = [sorted_b[0]]
        for b in sorted_b[1:]:
            if b - filtered[-1] >= 1.0: # 1초 미만 간격의 경계는 무시
                filtered.append(b)
        return filtered

    def build_fragments(self, source_id, evidences, boundaries):
        """[STEP 4] Evidence segments를 Boundary 기준으로 분할 및 매핑"""
        final_fragments = []
        
        for ev in evidences:
            ev_start, ev_end = ev["start"], ev["end"]
            
            # 해당 evidence 범위 내의 경계점 추출
            cuts = [b for b in boundaries if ev_start < b < ev_end]
            cuts = sorted(list(set([ev_start] + cuts + [ev_end])))
            
            for i in range(len(cuts)-1):
                start, end = round(cuts[i], 2), round(cuts[i+1], 2)
                if end - start < 0.2: continue 
                
                sf_id = f"SF_{uuid.uuid4().hex[:6].upper()}_{source_id}"
                final_fragments.append({
                    "fragment_id": sf_id,
                    "source_id": source_id,
                    "start": start,
                    "end": end,
                    "semantic": {
                        "summary": (ev.get("text")[:50] + "...") if ev.get("text") else "Visual/Audio Context",
                        "topic": "general",
                        "transcript_refs": [ev["fragment_id"]],
                        "evidence_refs": [ev["fragment_id"]]
                    },
                    "structural": {
                        "role": "context",
                        "edit_value": 0.5, # Default / User Rescored
                        "market_value": 0.5, # Static Market Value
                        "duration": end - start
                    },
                    "continuity": {},
                    "confidence": ev.get("confidence", 1.0)
                })
        return final_fragments

    def classify_role(self, fragment, total_duration, intent_seed):
        """[STEP 4] Role 분류 규칙 (v3.2.1 정밀화)"""
        start, end = fragment["start"], fragment["end"]
        edit_value = fragment["structural"]["edit_value"]
        
        start_ratio = start / total_duration if total_duration > 0 else 0
        end_ratio = end / total_duration if total_duration > 0 else 0
        
        if start_ratio < 0.2 and edit_value > 0.6: return "hook"
        if end_ratio > 0.9: return "closing"
        if edit_value > 0.8: return "payoff"
        if edit_value < 0.2: return "filler"
            
        return "context"

    def calculate_edit_value(self, evidence_refs, all_evidences, intent_seed):
        """[STEP 4] Edit Value 계산 (v3.2.1 보완: Dict 기반 가중치 및 전체 종합)"""
        ref_evs = [e for e in all_evidences if e["fragment_id"] in evidence_refs]
        if not ref_evs: return 0.5
        
        # Intent Seed - priority_axis (Dict)
        priority = intent_seed.get("priority_axis", {})
        if not isinstance(priority, dict):
            priority = {"visual": 1.0, "speech": 1.0, "emotion": 1.0}
            
        w_visual = priority.get("visual", 1.0)
        w_speech = priority.get("speech", 1.0)
        w_emotion = priority.get("emotion", 1.0)

        total_score = 0.0
        for ev in ref_evs:
            s_vis = ev.get("motion_score", 0.0)
            s_sp = 1.0 if ev.get("text") else 0.0
            s_em = ev.get("audio_energy", 0.0)
            
            ev_score = (s_sp * w_speech * 0.4) + (s_vis * w_visual * 0.3) + (s_em * w_emotion * 0.2)
            if ev.get("scene_change"): ev_score += 0.05
            if ev.get("keyframe"): ev_score += 0.05
            
            total_score += ev_score
            
        avg_score = total_score / len(ref_evs)
        return max(0.0, min(1.0, avg_score))

    def calculate_continuity(self, current, prev):
        """[STEP 4] Continuity 4요소 계산"""
        continuity = {
            "topic_similarity": 0.5, "time_proximity": 1.0,
            "sentiment_continuity": 0.5, "narrative_flow": 0.5
        }
        if prev:
            gap = current["start"] - prev["end"]
            continuity["time_proximity"] = max(0.0, 1.0 - (abs(gap) / 2.0))
            continuity["topic_similarity"] = 0.7 if current["semantic"]["topic"] == prev["semantic"]["topic"] else 0.4
        return continuity

    def apply_merge_split(self, fragments, boundaries, total_duration):
        """[STEP 4] Merge (2s 미만) 및 Split (60s 초과) 실제 보정"""
        if not fragments: return []
        
        is_fast_path = total_duration <= 60.0
        # [STEP 10-I.5.2] Fast Path 시 2.5초 미만 병합 (기존 3.5초는 너무 큼), 일반 2.0초
        merge_threshold = 2.5 if is_fast_path else 2.0
        
        # 1. Merge (Threshold 미만 조각 제거)
        res = []
        for frag in fragments:
            if not res:
                res.append(frag)
                continue
            
            last = res[-1]
            if last["structural"]["duration"] < merge_threshold or frag["structural"]["duration"] < merge_threshold:
                # 병합
                last["end"] = frag["end"]
                last["structural"]["duration"] = last["end"] - last["start"]
                for key in ["evidence_refs", "transcript_refs"]:
                    last["semantic"][key] = list(set(last["semantic"][key] + frag["semantic"][key]))
                res[-1] = last
            else:
                res.append(frag)
        
        # [STEP 10-I.5.2] 조각 수 강제 제한 (Fast Path: 8~18개)
        # 너무 많으면 의미적으로 뭉치고, 너무 적으면 30초 고정이 됨.
        if is_fast_path and len(res) > 18:
            print(f"[SEMANTIC] Fast Path Limit: {len(res)} -> 18 merging...")
            while len(res) > 18:
                # 가장 짧은 조각을 찾아 인접 조각과 병합
                min_idx = -1
                min_dur = 9999.0
                for i, f in enumerate(res):
                    if f["structural"]["duration"] < min_dur:
                        min_dur = f["structural"]["duration"]
                        min_idx = i
                
                # 병합 방향 결정 (앞 또는 뒤)
                if min_idx == 0:
                    merge_to = 1
                elif min_idx == len(res) - 1:
                    merge_to = min_idx - 1
                else:
                    # 앞뒤 중 더 짧은 쪽으로 병합
                    prev_dur = res[min_idx-1]["structural"]["duration"]
                    next_dur = res[min_idx+1]["structural"]["duration"]
                    merge_to = min_idx - 1 if prev_dur < next_dur else min_idx + 1
                
                # 병합 실행
                target = res[min_idx]
                dest = res[merge_to]
                
                new_start = min(target["start"], dest["start"])
                new_end = max(target["end"], dest["end"])
                
                dest["start"] = new_start
                dest["end"] = new_end
                dest["structural"]["duration"] = new_end - new_start
                for key in ["evidence_refs", "transcript_refs"]:
                    dest["semantic"][key] = list(set(dest["semantic"][key] + target["semantic"][key]))
                
                res.pop(min_idx)
                # res[merge_to] 는 이미 업데이트됨
        
        # 2. Split (60초 초과 분할 시도)
        final = []
        for frag in res:
            if frag["structural"]["duration"] > 60.0:
                # 내부 경계 탐색
                mid = frag["start"] + 30.0
                cuts = [b for b in boundaries if frag["start"] + 5.0 < b < frag["end"] - 5.0]
                if cuts:
                    # 중간에 가장 가까운 경계에서 쪼갬
                    cut = sorted(cuts, key=lambda x: abs(x - mid))[0]
                    # 쪼개기 (단순화: 2개로 분할)
                    f1 = frag.copy(); f1["end"] = cut; f1["structural"] = frag["structural"].copy(); f1["structural"]["duration"] = cut - f1["start"]
                    f2 = frag.copy(); f2["start"] = cut; f2["structural"] = frag["structural"].copy(); f2["structural"]["duration"] = f2["end"] - cut
                    final.extend([f1, f2])
                    continue

                frag["fallback_reason"] = "split_candidate_too_long"
            final.append(frag)
                
        return final

    def calculate_confidence(self, fragment):
        return 0.9 if fragment["semantic"]["summary"] != "Visual/Audio Context" else 0.7

    def calculate_fallback_reason(self, fragment):
        """[STEP 4] Fallback Reason 정합성 보완 (v3.2.1)"""
        reasons = []
        # 1. Continuity Placeholder
        if fragment["continuity"].get("sentiment_continuity") == 0.5:
            reasons.append("continuity_placeholder")
        
        # 2. Split Candidate (오직 60초 초과 시에만 기록)
        duration = fragment["structural"].get("duration", 0)
        if duration > 60.0:
            reasons.append("split_candidate_too_long")
            
        return ", ".join(reasons) if reasons else None

    def _get_default_intent(self):
        return {"priority_axis": "balanced", "tone": "general"}

    # ═══════════════════════════════════════════════════════════════════
    #   [STEP 5] User Intent Rescoring (Refinement)
    # ═══════════════════════════════════════════════════════════════════

    def rescore_all_fragments(self, source_id: str, user_intent: dict):
        """[STEP 5] User Intent에 기반하여 모든 Semantic Fragments의 edit_value 재계산"""
        fragments = self.bams.get_semantic_fragments(source_id)
        if not fragments: return []

        evidences = self.bams.get_evidence_board(source_id)

        rescored = []
        for frag in fragments:
            updated_frag = self.rescore_fragment(frag, evidences, user_intent)
            rescored.append(updated_frag)

        # DB 업데이트
        self.bams.save_semantic_fragments(source_id, rescored)
        return rescored

    def rescore_fragment(self, fragment, evidences, user_intent):
        """
        [STEP 5] 단일 조각의 의도 반영 점수 재계산
        - must_keep (+0.2)
        - avoid (-0.3)
        - priority_axis (visual/speech/emotion)
        - tone match
        """
        # 1. 원본 Evidence 기반 기초 점수 재계산 (User Intent 반영)
        base_user_value = self.calculate_edit_value(
            fragment["semantic"].get("evidence_refs", []), 
            evidences, 
            user_intent 
        )
        
        # 2. Keywords Matching
        must_keep_bonus = 0.0
        if self.match_must_keep(fragment, user_intent.get("must_keep", [])):
            must_keep_bonus = 0.2
            
        avoid_penalty = 0.0
        if self.match_avoid(fragment, user_intent.get("avoid", [])):
            avoid_penalty = -0.3
            
        # 3. Tone Match (Placeholder)
        tone_bonus = 0.0
        if user_intent.get("tone") and user_intent["tone"] != "general":
             tone_bonus = 0.05 

        # 4. 종합 및 Clamp (User 전용 점수 갱신)
        final_value = base_user_value + must_keep_bonus + avoid_penalty + tone_bonus
        fragment["structural"]["edit_value"] = max(0.0, min(1.0, final_value))
        
        return fragment

    def match_must_keep(self, fragment, must_keep_keywords):
        """[STEP 5] Must Keep 키워드가 조각의 의미 정보에 포함되는지 확인"""
        if not must_keep_keywords: return False
        
        # summary, topic, transcript 힌트 종합
        text_pool = f"{fragment['semantic'].get('summary', '')} {fragment['semantic'].get('topic', '')}".lower()
        
        for word in must_keep_keywords:
            if word.lower() in text_pool:
                return True
        return False

    def match_avoid(self, fragment, avoid_keywords):
        """[STEP 4] Avoid 키워드가 조각의 의미 정보에 포함되는지 확인"""
        if not avoid_keywords: return False
        
        text_pool = f"{fragment['semantic'].get('summary', '')} {fragment['semantic'].get('topic', '')}".lower()
        
        for word in avoid_keywords:
            if word.lower() in text_pool:
                return True
        return False
