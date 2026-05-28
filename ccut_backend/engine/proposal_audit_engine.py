import os
import json
from typing import List, Dict, Any
from ai.narrative.reviewer_swarm_contract import ReviewResult, ProposalSwarmAudit

class ProposalAuditEngine:
    """
    [STEP 11-A] ProposalAuditEngine
    Evaluates proposal sequences under a swarm of synthetic reviewer personas.
    Computes objective metrics and generates qualitative text feedback.
    """
    def __init__(self, bams_manager):
        self.bams = bams_manager
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        reg_path = os.path.join(os.path.dirname(__file__), "..", "ai", "narrative", "reviewer_registry.json")
        if os.path.exists(reg_path):
            with open(reg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Fallback inline registry if file missing
        return {}

    def audit_proposal(self, proposal: Dict[str, Any], source_id: str) -> Dict[str, Any]:
        """
        Evaluates a single proposal's sequence and formats a ProposalSwarmAudit object.
        """
        sequence = proposal.get("sequence", [])
        proposal_id = proposal.get("proposal_id", "PROP_UNKNOWN")
        mode = proposal.get("mode", "B")
        
        # 1. Gather emotional timeline and reaction signals
        from ai.narrative.emotion_timeline import EmotionalTimeline
        from ai.narrative.reaction_signal_detector import ReactionSignalDetector
        
        try:
            et = EmotionalTimeline(self.bams)
            timeline = et.build_timeline(source_id)
        except Exception:
            timeline = []

        try:
            rsd = ReactionSignalDetector(self.bams)
            reaction_signals = rsd.detect_signals(source_id)
        except Exception:
            reaction_signals = {}
            
        timeline_map = {item["fragment_id"]: item for item in timeline}

        # 2. Compute sequence-wide editing metrics
        num_clips = len(sequence)
        if num_clips == 0:
            return self._build_empty_audit(proposal_id, mode)
            
        durations = []
        roles = []
        scenery_count = 0
        reaction_count = 0
        main_count = 0
        short_clips = 0  # < 3.0s
        long_clips = 0   # > 8.0s
        consecutive_scenery = 0
        max_consecutive_scenery = 0
        
        for f in sequence:
            dur = float(f.get("duration") or f.get("duration_sec") or 5.0)
            durations.append(dur)
            
            role = f.get("structural", {}).get("role", "main")
            roles.append(role)
            
            if role == "scenery":
                scenery_count += 1
                consecutive_scenery += 1
                max_consecutive_scenery = max(max_consecutive_scenery, consecutive_scenery)
            else:
                consecutive_scenery = 0
                if role == "reaction":
                    reaction_count += 1
                else:
                    main_count += 1
                    
            if dur < 3.0:
                short_clips += 1
            elif dur > 8.0:
                long_clips += 1
                
        avg_duration = sum(durations) / num_clips
        scenery_ratio = scenery_count / num_clips
        reaction_ratio = reaction_count / num_clips
        short_ratio = short_clips / num_clips
        
        # 3. Swarm Evaluation loop
        reviews = []
        for persona_id, conf in self.registry.items():
            weights = conf.get("weights", {})
            pref_pacing = conf.get("pacing_preference", "medium")
            
            # --- Scoring Metric 1: Cinematic Flow ---
            flow_score = 0.5
            if persona_id == "documentary_director":
                # Prefers slow/medium pacing, presence of reaction and scenery, and emotional shifts
                if avg_duration >= 5.0 and reaction_count > 0:
                    flow_score = min(1.0, 0.6 + (reaction_ratio * 0.5) + (scenery_ratio * 0.3))
                else:
                    flow_score = max(0.1, 0.4 - (short_ratio * 0.4))
            elif persona_id == "youtube_vlogger":
                # Prefers fast cuts, dialogue hooks, low scenery
                if avg_duration <= 5.0 and scenery_ratio < 0.2:
                    flow_score = min(1.0, 0.7 + (short_ratio * 0.4) - (scenery_ratio * 0.5))
                else:
                    flow_score = max(0.2, 0.5 - (scenery_ratio * 0.6))
            elif persona_id == "cinematic_editor":
                # Prefers moderate pacing, high reaction count, and low consecutive scenery
                if 4.0 <= avg_duration <= 8.0 and max_consecutive_scenery <= 1:
                    flow_score = min(1.0, 0.7 + (reaction_ratio * 0.6))
                else:
                    flow_score = max(0.3, 0.6 - (max_consecutive_scenery * 0.2))
            elif persona_id == "shorts_addict":
                if avg_duration <= 3.0:
                    flow_score = 0.9
                else:
                    flow_score = max(0.1, 1.0 - (avg_duration * 0.08))
            else:  # general_viewer
                if 4.0 <= avg_duration <= 7.0:
                    flow_score = 0.8
                else:
                    flow_score = 0.6
                    
            # --- Scoring Metric 2: Boredom ---
            boredom_score = 0.2
            if scenery_ratio > 0.4 or max_consecutive_scenery >= 2 or avg_duration > 9.0:
                boredom_score = min(1.0, 0.2 + (scenery_ratio * 0.8) + (max_consecutive_scenery * 0.15))
            else:
                boredom_score = max(0.05, 0.2 - (short_ratio * 0.3))
                
            # Shorts addict and YouTube vlogger get bored much faster
            if persona_id == "shorts_addict":
                boredom_score = min(1.0, boredom_score * 1.6)
            elif persona_id == "youtube_vlogger":
                boredom_score = min(1.0, boredom_score * 1.3)
            elif persona_id == "documentary_director":
                boredom_score = max(0.05, boredom_score * 0.5)
                
            # --- Scoring Metric 3: Pacing Fatigue ---
            fatigue_score = 0.1
            if short_ratio > 0.4 or avg_duration < 3.5:
                fatigue_score = min(1.0, 0.1 + (short_ratio * 0.8) - (reaction_ratio * 0.3))
            else:
                fatigue_score = max(0.0, 0.1 - (scenery_ratio * 0.2))
                
            # Documentary director and cinematic editor suffer high fatigue from rapid cuts
            if persona_id == "documentary_director":
                fatigue_score = min(1.0, fatigue_score * 1.5)
            elif persona_id == "cinematic_editor":
                fatigue_score = min(1.0, fatigue_score * 1.3)
            elif persona_id == "shorts_addict":
                fatigue_score = max(0.0, fatigue_score * 0.2)
                
            # --- Scoring Metric 4: Reaction Preservation ---
            reaction_pres_score = 0.5
            if reaction_count > 0:
                reaction_pres_score = min(1.0, 0.5 + (reaction_ratio * 1.2))
            else:
                reaction_pres_score = max(0.1, 0.2)
                
            # Reviewers with reaction focus weight it higher
            if "reaction pacing" in conf.get("focus", []) or "delayed reaction" in conf.get("focus", []):
                reaction_pres_score = min(1.0, reaction_pres_score * 1.2)
            if persona_id == "shorts_addict":
                reaction_pres_score = max(0.1, reaction_pres_score * 0.5)
                
            # --- Scoring Metric 5: Scenery Overuse ---
            scenery_overuse = 0.1
            if scenery_ratio > 0.3 or max_consecutive_scenery >= 2:
                scenery_overuse = min(1.0, 0.1 + (scenery_ratio * 1.3) + (max_consecutive_scenery * 0.1))
            else:
                scenery_overuse = max(0.0, scenery_ratio * 0.5)
                
            # --- Overall Rating Calculation ---
            # Blend based on weights
            # Rating = Flow - PacingFatigue - Boredom + Reaction - SceneryOveruse (normalized)
            raw_rating = (
                (flow_score * weights.get("cinematic_flow", 1.0))
                - (fatigue_score * weights.get("pacing_fatigue", 1.0))
                - (boredom_score * weights.get("boredom", 1.0))
                + (reaction_pres_score * weights.get("reaction_preservation", 1.0))
                - (scenery_overuse * weights.get("scenery_overuse", 1.0))
            )
            
            # Normalize to 0.0 - 1.0 range
            overall_rating = max(0.1, min(1.0, 0.5 + (raw_rating / 4.0)))
            
            # Generate critique text
            critique = self._generate_critique(
                persona_id, conf["name"], avg_duration, scenery_ratio, reaction_ratio,
                max_consecutive_scenery, flow_score, boredom_score, fatigue_score, overall_rating
            )
            
            reviews.append(ReviewResult(
                persona_id=persona_id,
                name=conf["name"],
                cinematic_flow_score=round(flow_score, 2),
                boredom_score=round(boredom_score, 2),
                pacing_fatigue_score=round(fatigue_score, 2),
                reaction_preservation_score=round(reaction_pres_score, 2),
                scenery_overuse_score=round(scenery_overuse, 2),
                overall_rating=round(overall_rating, 2),
                critique=critique
            ))
            
        # 4. Compute composite averages
        avg_rating = sum(r.overall_rating for r in reviews) / len(reviews)
        composite = {
            "cinematic_flow": round(sum(r.cinematic_flow_score for r in reviews) / len(reviews), 2),
            "boredom": round(sum(r.boredom_score for r in reviews) / len(reviews), 2),
            "pacing_fatigue": round(sum(r.pacing_fatigue_score for r in reviews) / len(reviews), 2),
            "reaction_preservation": round(sum(r.reaction_preservation_score for r in reviews) / len(reviews), 2),
            "scenery_overuse": round(sum(r.scenery_overuse_score for r in reviews) / len(reviews), 2)
        }
        
        return {
            "proposal_id": proposal_id,
            "mode": mode,
            "average_overall_rating": round(avg_rating, 2),
            "reviews": [r.dict() for r in reviews],
            "composite_metrics": composite
        }

    def _generate_critique(self, pid: str, name: str, avg_dur: float, scenery_ratio: float, 
                           reaction_ratio: float, max_con_scenery: int, flow: float, boredom: float, 
                           fatigue: float, rating: float) -> str:
        """
        Generates contextual natural language critiques depending on the persona and scores.
        """
        if pid == "documentary_director":
            if rating >= 0.75:
                return (
                    f"호흡이 매우 인상적입니다. 평균 컷 길이({avg_dur:.1f}초)가 길어서 인물의 감정과 "
                    f"현장의 공기를 충분히 담아내고 있습니다. 리액션 비율({reaction_ratio:.1%})도 적절하여 "
                    f"인물 간의 관계와 감정 여운이 잘 살아납니다. 다큐멘터리 연출 의도에 아주 잘 맞닿아 있습니다."
                )
            elif fatigue > 0.5:
                return (
                    f"컷이 너무 자주 끊겨 감정의 축적이 어렵습니다. 평균 컷 길이({avg_dur:.1f}초)가 짧아 "
                    f"마치 쇼츠를 보듯 정신이 없습니다. 시청자가 영상의 내면적 가치를 소화할 수 있도록 "
                    f"리액션 컷과 정적인 호흡의 여백을 더 늘릴 것을 권합니다."
                )
            else:
                return (
                    f"전체적으로 나쁘지 않으나 호흡이 아주 살짝 아쉽습니다. 풍경의 비율을 조절하고 "
                    f"이야기의 중심이 되는 인물의 리액션 컷을 1~2초만 더 길게 확보한다면 서사의 여운이 한층 더 굳건해질 것입니다."
                )
                
        elif pid == "youtube_vlogger" or pid == "travel_vlogger":
            if rating >= 0.7:
                return (
                    f"빠르고 깔끔한 전개입니다! 컷 전환 속도가 시청자 이탈을 막기에 적합하며, 풍경 컷({scenery_ratio:.1%})도 "
                    f"분위기를 환기하는 브릿지로서의 역할만 담백하게 수행하고 있습니다. 영상 편집에 텐션이 잘 붙어 있습니다."
                )
            elif boredom > 0.5:
                return (
                    f"편집 속도가 너무 늘어집니다. 컷 하나당 평균 {avg_dur:.1f}초는 요즘 유튜브 트렌드에 비하면 "
                    f"시청자들이 중간에 이탈할 위험이 매우 높습니다. 불필요한 풍경이나 긴 침묵을 덜어내고 핵심 대화 위주로 속도감 있게 줄여야 합니다."
                )
            else:
                return (
                    f"중간에 템포가 다소 처지는 구간이 보입니다. 풍경이 2회 이상 연속으로 이어지는 부분({max_con_scenery}회)이나 "
                    f"말이 없는 조각의 길이를 조금만 더 타이트하게 잘라낸다면 유튜브 편집안으로서 매우 매끄러워질 것입니다."
                )
                
        elif pid == "cinematic_editor":
            if rating >= 0.75:
                return (
                    f"쇼트와 쇼트 사이의 유기적 흐름이 뛰어납니다. 대화 구간 뒤에 배치된 리액션 컷의 타이밍이 기품 있게 잡혀 있습니다. "
                    f"긴장과 이완의 대비가 뚜렷하며, 풍경과 인물이 교차하는 방식에서 고전 영화적인 리듬감이 느껴집니다."
                )
            elif max_con_scenery >= 2:
                return (
                    f"시각적 연결성(Visual Continuity)이 다소 느슨합니다. 풍경 컷이 연속으로 붙어 흐름이 끊기거나, "
                    f"감정의 연쇄를 이어갈 인물의 리액션이 부족해 장면 간 결속력이 깨져 보입니다. 대비 컷의 템포를 조절해 보세요."
                )
            else:
                return (
                    f"장면 전개는 안정적이나 영화적 고유의 리듬 변화(Dramatic Curve)가 평이합니다. "
                    f"감정의 변곡점을 더 살릴 수 있는 방향으로 일부 조각의 배치 우선순위를 미세 조정할 것을 추천합니다."
                )
                
        elif pid == "shorts_addict":
            if avg_dur <= 3.5:
                return "10초 안에 시선을 끕니다. 지루한 틈이 없이 컷이 빠르게 넘어가서 아주 좋습니다!"
            else:
                return (
                    f"평균 {avg_dur:.1f}초는 너무 길어요. 3초 이상 말이 없거나 멈춰 있는 풍경 컷이 나올 때마다 "
                    f"바로 스와이프해서 다음 영상으로 넘어가고 싶어집니다. 대화나 반응 속도를 극도로 단축해야 합니다."
                )
                
        elif pid == "emotional_purist" or pid == "emotion_centric":
            if rating >= 0.75:
                return f"장면에 담긴 인물의 정서적 밀도가 매우 높습니다. 리액션 컷({reaction_ratio:.1%})과 적절한 템포의 교차가 감정 이입을 돕습니다."
            else:
                return "감정적인 여운을 길게 가져갈 수 있도록 인물의 얼굴과 표정이 담긴 조각의 노출 시간을 조금 더 길게 유지해 주길 기대합니다."

        elif pid == "slow_breather":
            if rating >= 0.75:
                return "마음이 편안해지는 속도입니다. 조용하고 정적인 컷들의 배치가 훌륭한 시각적 휴식을 제공합니다."
            else:
                return "호흡이 너무 조급합니다. 자막과 오디오가 비어 있는 '숨쉴 틈'을 최소 2초 이상 배치하여 뇌의 휴식 시간을 벌어줘야 합니다."

        elif pid == "fast_tempo":
            if rating >= 0.75:
                return f"매우 역동적인 에너지가 흐릅니다. 빠른 컷 전환과 높은 움직임이 지루함을 완벽히 원천 차단했습니다."
            else:
                return f"평균 컷 길이가 {avg_dur:.1f}초로 너무 루즈합니다. 템포를 끌어올리기 위해 풍경 컷의 길이를 과감히 절반으로 쳐내야 합니다."

        elif pid == "info_centric":
            if rating >= 0.75:
                return "구조화가 잘 된 정보 제공용 구성입니다. 불필요한 공백 없이 대사와 자막 정보가 촘촘히 연결되어 인지적 흡수가 잘 됩니다."
            else:
                return "내러티브 논리 구조가 산만해 정보 전달력이 약합니다. 훅-메인-페이오프 순서를 명확히 지키고 쓸데없는 리액션 컷을 줄이길 권장합니다."

        else:  # general_viewer
            if 0.4 <= boredom <= 0.6 and 0.4 <= fatigue <= 0.6:
                return "너무 지루하지도 않고 너무 정신없지도 않은 아주 무난하고 편안하게 감상할 수 있는 편집 템포입니다."
            elif boredom > 0.6:
                return "약간 지루함이 느껴집니다. 대화가 없는 빈 화면이나 풍경 장면들이 조금만 짧아지면 끝까지 집중하기 편할 것 같습니다."
            else:
                return "컷이 너무 휙휙 지나가는 느낌이라 내용 파악이 살짝 어렵네요. 조금만 템포를 늦춰서 안정적으로 전개했으면 좋겠습니다."

    def _build_empty_audit(self, proposal_id: str, mode: str) -> Dict[str, Any]:
        return {
            "proposal_id": proposal_id,
            "mode": mode,
            "average_overall_rating": 0.0,
            "reviews": [],
            "composite_metrics": {
                "cinematic_flow": 0.0,
                "boredom": 0.0,
                "pacing_fatigue": 0.0,
                "reaction_preservation": 0.0,
                "scenery_overuse": 0.0
            }
        }
