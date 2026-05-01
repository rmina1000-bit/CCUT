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

        # [STEP 10-I.5.9] Diagnostic Logging
        print(f"\n{'='*60}")
        print(f"[SEMANTIC DIAGNOSTIC] Source ID: {source_id}")
        
        raw_vfs = [e for e in evidences if e.get("fragment_id", "").startswith("VF")]
        print(f"[SEMANTIC DIAGNOSTIC] raw/VF fragment count: {len(raw_vfs)}")
        if raw_vfs:
            print(f"[SEMANTIC DIAGNOSTIC] raw/VF duration list (first 10): {[round(e['end']-e['start'], 1) for e in raw_vfs[:10]]}")
            
        whisper_segs = [e for e in evidences if e.get("worker_name") == "whisper_segments"]
        print(f"[SEMANTIC DIAGNOSTIC] transcript/whisper segment count: {len(whisper_segs)}")
        if whisper_segs:
            print(f"[SEMANTIC DIAGNOSTIC] transcript/whisper duration list (first 10): {[round(e['end']-e['start'], 1) for e in whisper_segs[:10]]}")
            
        worker_counts = {}
        for ev in evidences:
            wn = ev.get("worker_name", "unknown")
            worker_counts[wn] = worker_counts.get(wn, 0) + 1
        print(f"[SEMANTIC DIAGNOSTIC] Evidence type counts: {worker_counts}")

        # 3. 경계 후보 생성 (Evidence-driven: scene, silence, motion, topic)
        boundaries = self.create_fragment_boundaries(evidences, total_duration)
        
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
        
        # [SEMANTIC DIAGNOSTIC] Final summary
        print(f"[SEMANTIC DIAGNOSTIC] Final semantic duration list (first 20): {[round(f['structural']['duration'], 1) for f in final_fragments[:20]]}")
        print(f"{'='*60}\n")

        print(f"[SEMANTIC] {len(final_fragments)} fragments generated for {source_id}")
        return final_fragments

    def create_fragment_boundaries(self, evidences, total_duration=0):
        """
        [STEP 10-I.5.3] Text-first 경계 후보 생성
        - whisper_segments: 가장 강력한 텍스트/문장 경계
        - scene_change: 시각적 전환
        - silence: 오디오 중단
        - VF artificial boundaries (30s)는 의도적으로 제외
        """
        boundaries = [0.0]
        
        # 1. Whisper Segments (Text-first priority)
        whisper_evs = [e for e in evidences if e.get("worker_name") == "whisper_segments"]
        for ev in whisper_evs:
            boundaries.append(ev["start"])
            boundaries.append(ev["end"])

        # 2. Scene Changes & Silence from all evidences
        for ev in evidences:
            wn = ev.get("worker_name", "unknown")
            # [STEP 10-I.5.9] Skip boundaries from workers that just repeat VF boundaries
            if wn in ["audio", "signal_processor", "whisper"]:
                continue

            if ev.get("scene_change") and isinstance(ev["scene_change"], list):
                for ts in ev["scene_change"]:
                    boundaries.append(ts)
            
            # Silence detection (usually from specialized silence detectors)
            if wn == "silence" or ev.get("audio_energy", 1.0) < 0.05:
                boundaries.append(ev["start"])

        # [STEP 10-I.5.9] Boundary source distribution log
        whisper_boundary_count = len(whisper_evs) * 2
        scene_boundary_count = sum(len(ev["scene_change"]) for ev in evidences if ev.get("scene_change") and isinstance(ev["scene_change"], list))
        silence_boundary_count = sum(1 for ev in evidences if (ev.get("worker_name") == "silence" or (ev.get("audio_energy", 1.0) < 0.05 and ev.get("worker_name") not in ["audio", "signal_processor", "whisper"])))
        
        print(f"[SEMANTIC DIAGNOSTIC] Boundary distribution:")
        print(f"  - whisper_segments: {whisper_boundary_count}")
        print(f"  - scene_change: {scene_boundary_count}")
        print(f"  - silence/audio_energy: {silence_boundary_count}")

        # [STEP 10-I.5.3] 0.0과 total_duration은 항상 포함 (evidences에서 계산)
        if evidences:
            all_ends = [e["end"] for e in evidences]
            if all_ends:
                boundaries.append(max(all_ends))
        
        # [STEP 10-I.5.9] Add total_duration from source if available
        if total_duration > 0:
            boundaries.append(total_duration)

        # 중복 및 너무 가까운 경계 제거
        unique_b = sorted(list(set([round(b, 2) for b in boundaries])))
        print(f"[SEMANTIC DIAGNOSTIC] Raw semantic boundary count (unique): {len(unique_b)}")
        
        sorted_b = unique_b
        if not sorted_b: return [0.0]
        
        filtered = [sorted_b[0]]
        for b in sorted_b[1:]:
            # [STEP 10-I.5.9] 텍스트 기반인 경우 조금 더 촘촘하게 (0.8초)
            # 단, 너무 뒤로 밀리지 않도록 함
            if b - filtered[-1] >= 0.8:
                filtered.append(b)
        
        # 마지막 경계가 total_duration보다 작으면 추가 (전체 영상 커버 보장)
        if total_duration > 0 and filtered[-1] < total_duration - 0.5:
             filtered.append(total_duration)
             
        return filtered

    def build_fragments(self, source_id, evidences, boundaries):
        """[STEP 10-I.5.3] Global boundaries 기반으로 조각 생성 (30s 경계 무관)"""
        final_fragments = []
        
        # boundaries는 이미 0.0부터 total_duration까지 정렬되어 있음
        for i in range(len(boundaries)-1):
            start, end = round(boundaries[i], 2), round(boundaries[i+1], 2)
            duration = round(end - start, 2)
            if duration < 0.2: continue 
            
            # 해당 시간 범위에 걸쳐 있는 모든 evidences 찾기
            overlapping_evs = [
                ev for ev in evidences 
                if not (ev["end"] <= start or ev["start"] >= end)
            ]
            
            if not overlapping_evs:
                # Evidence가 없는 구간 (그럴 수 없지만 방어코드)
                continue
            
            # 첫 번째 Evidence를 기본 정보로 사용 (Summary 등)
            primary_ev = overlapping_evs[0]
            
            # 여러 evidence의 텍스트 병합
            combined_text = " ".join([e.get("text", "") for e in overlapping_evs if e.get("text")]).strip()
            
            sf_id = f"SF_{uuid.uuid4().hex[:6].upper()}_{source_id}"
            final_fragments.append({
                "fragment_id": sf_id,
                "source_id": source_id,
                "start": start,
                "end": end,
                "semantic": {
                    "summary": (combined_text[:50] + "...") if combined_text else "Visual/Audio Context",
                    "topic": primary_ev.get("topic", "general"),
                    "transcript_refs": [e["fragment_id"] for e in overlapping_evs],
                    "evidence_refs": [e["fragment_id"] for e in overlapping_evs]
                },
                "structural": {
                    "role": "context",
                    "edit_value": 0.5,
                    "market_value": 0.5,
                    "duration": duration
                },
                "continuity": {},
                "confidence": max([e.get("confidence", 0.5) for e in overlapping_evs])
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
        """[STEP 10-I.5.3] Merge (3s 미만) 및 Split (20s 초과) 보정"""
        if not fragments: return []
        
        is_fast_path = total_duration <= 60.0
        # 3.0초 미만은 병합 시도 (Text-first 권장 최소 길이)
        merge_threshold = 3.0
        
        # 1. Merge (Threshold 미만 조각 제거)
        res = []
        for frag in fragments:
            if not res:
                res.append(frag)
                continue
            
            last = res[-1]
            # 너무 짧으면 이전 조각에 병합 (단, 병합 후 너무 길어지지 않는 경우)
            if last["structural"]["duration"] < merge_threshold:
                # 병합
                last["end"] = frag["end"]
                last["structural"]["duration"] = round(last["end"] - last["start"], 2)
                for key in ["evidence_refs", "transcript_refs"]:
                    last["semantic"][key] = list(set(last["semantic"][key] + frag["semantic"][key]))
                res[-1] = last
            else:
                res.append(frag)
        
        # [STEP 10-I.5.3] 조각 수 강제 제한 (8~18개)
        if is_fast_path and len(res) > 18:
            print(f"[SEMANTIC] Fast Path Limit: {len(res)} -> 18 merging...")
            while len(res) > 18:
                min_idx = -1
                min_dur = 9999.0
                for i, f in enumerate(res):
                    if f["structural"]["duration"] < min_dur:
                        min_dur = f["structural"]["duration"]
                        min_idx = i
                
                if min_idx == 0: merge_to = 1
                elif min_idx == len(res) - 1: merge_to = min_idx - 1
                else:
                    prev_dur = res[min_idx-1]["structural"]["duration"]
                    next_dur = res[min_idx+1]["structural"]["duration"]
                    merge_to = min_idx - 1 if prev_dur < next_dur else min_idx + 1
                
                target = res[min_idx]; dest = res[merge_to]
                dest["start"] = min(target["start"], dest["start"])
                dest["end"] = max(target["end"], dest["end"])
                dest["structural"]["duration"] = round(dest["end"] - dest["start"], 2)
                for key in ["evidence_refs", "transcript_refs"]:
                    dest["semantic"][key] = list(set(dest["semantic"][key] + target["semantic"][key]))
                res.pop(min_idx)
        
        # 2. Split (20초 초과 분할 시도)
        final = []
        for frag in res:
            duration = frag["structural"]["duration"]
            if duration > 20.0:
                # 내부 경계 탐색 (가장 중앙에 가까운 경계 찾기)
                mid = frag["start"] + (duration / 2.0)
                # 5초 정도의 여유를 둠 (너무 짧은 조각 방지)
                cuts = [b for b in boundaries if frag["start"] + 5.0 < b < frag["end"] - 5.0]
                
                if cuts:
                    cut = sorted(cuts, key=lambda x: abs(x - mid))[0]
                else:
                    # [STEP 10-I.5.9] Boundary가 전혀 없으면 강제 분할 (8~12초 가변 윈도우)
                    # 30초 고정 반복을 깨기 위해 가변성 부여
                    import random
                    cut = round(frag["start"] + 10.0 + random.uniform(-2.0, 2.0), 2)
                    if not (frag["start"] + 5.0 < cut < frag["end"] - 5.0):
                        cut = round(mid, 2)
                
                f1 = frag.copy(); f1["end"] = cut; f1["structural"] = frag["structural"].copy(); f1["structural"]["duration"] = round(cut - f1["start"], 2)
                f1["fragment_id"] = f"{frag['fragment_id']}_S1"
                
                f2 = frag.copy(); f2["start"] = cut; f2["structural"] = frag["structural"].copy(); f2["structural"]["duration"] = round(f2["end"] - cut, 2)
                f2["fragment_id"] = f"{frag['fragment_id']}_S2"
                
                # 재귀적으로 한 번 더 체크 (40초 초과 시 등)
                if f1["structural"]["duration"] > 20.0 or f2["structural"]["duration"] > 20.0:
                    sub_final = self.apply_merge_split([f1, f2], boundaries, total_duration)
                    final.extend(sub_final)
                else:
                    final.extend([f1, f2])
                continue
                
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
