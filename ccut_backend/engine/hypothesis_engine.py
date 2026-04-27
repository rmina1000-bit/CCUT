import os
import datetime
from archive.manager import bams

class HypothesisEngine:
    def __init__(self):
        pass

    def generate_quick_scan(self, source_id: str):
        """
        [STEP 3] Quick Scan + Hypothesis 생성 (Repaired v3.2.1)
        """
        source = bams.get_source(source_id)
        if not source: return None
        
        evidences = bams.get_evidence_board(source_id)
        fragments = bams.get_fragments_by_source(source_id)
        
        if not fragments:
            return {"status": "WAITING_FRAGMENTS", "progress": 0}

        # 1. 대표 이미지 3~7개 선정 (Opening, Mid, Ending 우선)
        rep_images = []
        num_frags = len(fragments)
        
        # 선정 지점 계산: 0, 0.25, 0.5, 0.75, 1.0 비율 지점
        indices = [0, num_frags // 4, num_frags // 2, (3 * num_frags) // 4, num_frags - 1]
        unique_indices = sorted(list(set([i for i in indices if 0 <= i < num_frags])))
        
        for i in unique_indices:
            f = fragments[i]
            # Keyframe 경로 (thumb_url 우선)
            intelligence = f.get("intelligence", {})
            keyframe_url = intelligence.get("thumb_url")
            if not keyframe_url:
                keyframe_url = f"http://localhost:8000/static/thumbnails/{f['fragment_id']}.jpg"
                
            rep_images.append({
                "time": f['start_time'],
                "keyframe": keyframe_url,
                "reason": "Opening" if i == 0 else ("Ending" if i == num_frags-1 else "Mid Sequence")
            })

        # 2. 실행 조건 체크 (Evidence 10% 이상 OR 대표 Keyframe 3개 이상)
        evidence_count = len([e for e in evidences if e.get('text') or e.get('audio_energy') > 0])
        progress = (evidence_count / num_frags) if num_frags else 0
        
        keyframe_count = len(rep_images)
        
        if progress < 0.1 and keyframe_count < 3:
             return {
                 "status": "WAITING_EVIDENCE", 
                 "progress": round(progress, 2),
                 "msg": "Waiting for at least 10% evidence or 3 representative keyframes"
             }

        # 3. 짧은 영상 요약 및 근거 (Heuristic Basis)
        full_text = " ".join([e.get('text', '') for e in evidences if e.get('text')])
        word_list = full_text.split()
        word_count = len(word_list)
        scene_count = len([e for e in evidences if e.get('scene_change')])
        motion_avg = sum([e.get('motion_score', 0) for e in evidences]) / max(1, len(evidences))
        
        if word_count > 15:
             summary_text = f"이 영상은 주로 '{' '.join(word_list[:8])}...' 등의 주제를 다루고 있습니다."
        else:
             summary_text = f"영상 신호 분석 결과 {num_frags}개의 의미 단위가 확인되며, 장면 전환({scene_count}회) 및 움직임({motion_avg:.2f})이 감지되었습니다."

        summary = {
            "text": summary_text,
            "summary_basis": {
                "text_refs": word_list[:5] if word_count > 0 else [],
                "scene_change_count": scene_count,
                "motion_avg": round(motion_avg, 2)
            },
            "confidence": round(min(0.9, 0.4 + (word_count / 100)), 2),
            "fallback_reason": None if word_count > 10 else "Low text density, used visual signals"
        }

        # 4. Hypothesis 및 Fallback Reason 보강
        total_duration = source.duration
        video_type = "daily"
        if total_duration < 65: video_type = "shorts"
        elif word_count / max(1, total_duration) > 0.8: video_type = "talk"
        
        recommended_dir = "감성형"
        if video_type == "shorts": recommended_dir = "쇼츠형"
        elif video_type == "talk": recommended_dir = "정보형"

        hypothesis = {
            "video_type": video_type,
            "core_elements": ["장면 전환", "인물 대화" if word_count > 0 else "시각적 흐름"],
            "recommended_direction": recommended_dir,
            "reason": f"영상 길이({int(total_duration)}s) 및 발화 밀도 데이터 기반 {video_type} 추정",
            "confidence": 0.68,
            "fallback_reason": "Low scene change variety" if scene_count < 2 else None
        }

        # 5. Default Intent Seed (source 필드 추가 보강)
        intent_seed = {
            "must_keep": [],
            "avoid": [],
            "tone": recommended_dir,
            "target_length": None,
            "priority_axis": {
                "visual": 1.2 if video_type == "daily" else 1.0,
                "speech": 1.2 if video_type == "talk" else 0.8,
                "emotion": 1.1
            },
            "source": "default_hypothesis" # [STEP 3 Repair]
        }

        result = {
            "source_id": source_id,
            "status": "QUICK_SCAN_READY",
            "partial": progress < 1.0,
            "evidence_progress": round(progress, 2),
            "representative_images": rep_images,
            "representative_images_fallback": "Available keyframes below minimum (3)" if keyframe_count < 3 else None,
            "summary": summary,
            "hypothesis": hypothesis,
            "questions": [
                "이 영상의 핵심이 맞습니까?",
                "꼭 살릴 장면은 무엇입니까?",
                "삭제할 장면은 무엇입니까?",
                "톤은 감성형 / 정보형 / 쇼츠형 중 무엇입니까?"
            ],
            "default_intent_seed": intent_seed
        }
        
        bams.save_quick_scan(source_id, result)
        return result

hypothesis_engine = HypothesisEngine()
