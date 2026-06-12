from sqlalchemy.orm import Session
from sqlalchemy import or_
from database import SessionLocal, engine, Base
from .db_models import SourceTable, FragmentTable, DecisionTable, ProgramTable, EvidenceTable, QuickScanTable
import uuid
import datetime
import os

Base.metadata.create_all(bind=engine)

class BAMSManager:
    def __init__(self):
        self.fragments = {}
        self.evidence_buffer = {} # [STEP 2] Worker 결과 메모리 버퍼
        self._load_all_to_memory()

    def _load_all_to_memory(self):
        try:
            with SessionLocal() as db:
                frags = db.query(FragmentTable).all()
                for f in frags:
                    class MockFrag:
                        def __init__(self, db_f):
                            self.fragment_id = db_f.fragment_id
                            self.start_time = db_f.start_time
                            self.end_time = db_f.end_time
                            self.intelligence = db_f.intelligence
                            self.status = db_f.status
                    self.fragments[f.fragment_id] = MockFrag(f)
        except Exception as e:
            print(f"DB Load error: {e}")

    def save_source(self, db: Session, source_data):
        """[STEP 1] 명시적 중복 체크 및 메타데이터 업데이트 (v3.2.1)"""
        existing = db.query(SourceTable).filter_by(source_id=source_data["source_id"]).first()
        if existing:
            # 0.0 에서 실제 데이터로 업데이트될 때 반영
            if source_data.get("duration"): existing.duration = source_data["duration"]
            if source_data.get("fps"): existing.fps = source_data["fps"]
            db.commit()
            return existing
        db_source = SourceTable(**source_data)
        db.add(db_source)
        db.commit()
        return db_source

    def get_source_by_hash(self, hash_value: str):
        """[STEP 1] Fingerprint 기반 소스 조회 (중복 방지)"""
        with SessionLocal() as db:
            return db.query(SourceTable).filter_by(hash_value=hash_value).first()

    def get_all_sources(self):
        with SessionLocal() as db:
            return db.query(SourceTable).all()

    def save_fragments(self, db: Session, fragments_list):
        for frag in fragments_list:
            db_frag = FragmentTable(**frag)
            db.add(db_frag)
            class MockFrag:
                def __init__(self, d):
                    self.fragment_id = d.get('fragment_id')
                    self.start_time = d.get('start_time')
                    self.end_time = d.get('end_time')
                    self.intelligence = d.get('intelligence')
                    self.status = d.get('status')
            self.fragments[frag["fragment_id"]] = MockFrag(frag)
        db.commit()

    def get_source(self, source_id: str):
        with SessionLocal() as db:
            return db.query(SourceTable).filter_by(source_id=source_id).first()

    def register_source(self, source):
        with SessionLocal() as db:
            s_dict = source.dict() if hasattr(source, 'dict') else source
            s_data = {
                "source_id": s_dict["source_id"],
                "file_path": s_dict["file_path"],
                "title": s_dict["title"],
                "duration": s_dict["duration"],
                "fps": s_dict.get("fps", 30.0),
                "hash_value": s_dict.get("hash_value") # [STEP 1]
            }
            self.save_source(db, s_data)

    def archive_fragments(self, fragments):
        with SessionLocal() as db:
            from archive.db_models import SemanticFragmentTable, SourceTable
            f_list = []
            for f in fragments:
                fd = f.dict() if hasattr(f, 'dict') else f
                intelligence = fd.get("intelligence", {})
                
                # [STEP 1] 정밀 타임스탬프 및 프록시 정보 보존
                intelligence.update({
                    "start_frame": fd.get("start_frame"),
                    "end_frame": fd.get("end_frame"),
                    "_proxy_video_path": fd.get("_proxy_video_path")
                })

                source_fps = 30.0
                source_id = fd.get("source_id") or "SRC_mock"
                if source_id and source_id != "SRC_mock":
                    src_obj = db.query(SourceTable).filter_by(source_id=source_id).first()
                    if src_obj and src_obj.fps:
                        source_fps = float(src_obj.fps)

                frag_id = fd.get("fragment_id") or fd.get("id")

                start_val = fd.get("start_time")
                if start_val is None:
                    start_val = fd.get("start")
                if start_val is None and frag_id:
                    sf_record = db.query(SemanticFragmentTable).filter_by(fragment_id=frag_id).first()
                    if sf_record and sf_record.start is not None:
                        start_val = sf_record.start
                if start_val is None:
                    start_frame = fd.get("start_frame")
                    if start_frame is not None:
                        start_val = float(start_frame) / source_fps

                end_val = fd.get("end_time")
                if end_val is None:
                    end_val = fd.get("end")
                if end_val is None and frag_id:
                    sf_record = db.query(SemanticFragmentTable).filter_by(fragment_id=frag_id).first()
                    if sf_record and sf_record.end is not None:
                        end_val = sf_record.end
                if end_val is None:
                    end_frame = fd.get("end_frame")
                    if end_frame is not None:
                        end_val = float(end_frame) / source_fps

                duration_val = fd.get("duration")
                if start_val is not None and end_val is not None:
                    duration_val = end_val - start_val
                elif duration_val is not None:
                    duration_val = float(duration_val)

                fd_data = {
                    "fragment_id": frag_id,
                    "source_id": source_id,
                    "start_time": start_val,
                    "end_time": end_val,
                    "duration": duration_val,
                    "intelligence": intelligence,
                    "status": fd.get("status", "AVAILABLE")
                }
                f_list.append(fd_data)
            self.save_fragments(db, f_list)

    def update_fragment_intelligence(self, fragment_id: str, intelligence: dict):
        """[STEP 1] Intelligence Deep Merge (유실 방지)"""
        with SessionLocal() as db:
            frag = db.query(FragmentTable).filter_by(fragment_id=fragment_id).first()
            if frag:
                existing = frag.intelligence or {}
                # 핵심 메타데이터 보존 (overwrite 방지)
                protected_fields = ["start_frame", "end_frame", "_proxy_video_path"]
                for field in protected_fields:
                    if field in existing and field not in intelligence:
                        intelligence[field] = existing[field]
                
                # 병합
                frag.intelligence = {**existing, **intelligence}
                db.commit()

    def update_fragment_boundary(self, fragment_id: str, start_time: float, end_time: float) -> bool:
        """[단계2] 경계 스냅 적용 — 물리 경계만 갱신."""
        with SessionLocal() as db:
            frag = db.query(FragmentTable).filter_by(fragment_id=fragment_id).first()
            if not frag:
                return False
            frag.start_time = float(start_time)
            frag.end_time = float(end_time)
            frag.duration = round(float(end_time) - float(start_time), 3)
            db.commit()
            return True

    def update_fragment_thumb(self, fragment_id: str, thumb_path: str):
        """[STEP 2] 썸네일 경로를 Frag intelligence 및 Evidence Board에 동기화"""
        filename = os.path.basename(thumb_path)
        thumb_url = f"/static/thumbnails/{filename}"

        with SessionLocal() as db:
            frag = db.query(FragmentTable).filter_by(fragment_id=fragment_id).first()
            if frag:
                # [STEP 10-I.5.27-E6-R3] Restore relative thumb URL
                frag.intelligence = {
                    **(frag.intelligence or {}),
                    "thumb_url": thumb_url
                }
                db.commit()
                
                # [STEP 2] Evidence Board sync (Keep local path or relative)
                self.update_evidence(fragment_id, {
                    "worker_name": "keyframe",
                    "keyframe": thumb_url,
                    "confidence": 1.0,
                    "fallback_reason": None
                })
                self.flush_evidence(fragment_id)
                print(f"[BAMS][REPAIR] Evidence Keyframe Updated: {fragment_id} -> {thumb_url}")

    def get_fragments_by_source(self, source_id: str):
        with SessionLocal() as db:
            frags = db.query(FragmentTable).filter_by(source_id=source_id).all()
            return [
                {
                    "fragment_id": f.fragment_id,
                    "id": f.fragment_id,
                    "source_id": f.source_id,
                    "start_time": f.start_time,
                    "end_time": f.end_time,
                    "duration": f.duration,
                    "intelligence": f.intelligence,
                    "status": f.status
                }
                for f in frags
            ]

    # ═══════════════════════════════════════════════════════════════════
    #   [STEP 2] Evidence Board MERGE ENGINE (Repaired)
    # ═══════════════════════════════════════════════════════════════════

    def update_evidence(self, fragment_id: str, data: dict):
        """[STEP 2] Worker 결과를 메모리 버퍼에 병합 (Field-level merge)"""
        if fragment_id not in self.evidence_buffer:
            self.evidence_buffer[fragment_id] = {
                "confidence": 0.0,
                "metadata_json": {},
                "worker_sources": {},
                "last_updated": datetime.datetime.min
            }
        
        buffer = self.evidence_buffer[fragment_id]
        incoming_conf = data.get("confidence", 1.0)
        existing_conf = buffer.get("confidence", 0.0)
        now = datetime.datetime.now()
        
        # 워커 소스 식별 (text -> whisper 등)
        worker_name = data.get("worker_name", "unknown")

        for k, v in data.items():
            if k in ["metadata_json", "worker_name", "confidence"]: continue
            
            # [STEP 2] Conflict Resolution: 
            # 1. 신뢰도 높은 값 우선
            # 2. 신뢰도 동일 시 최신 타임스탬프 우선
            if k not in buffer or incoming_conf > existing_conf or (incoming_conf == existing_conf and now > buffer["last_updated"]):
                buffer[k] = v
                buffer["worker_sources"][k] = worker_name

        if incoming_conf >= existing_conf:
            buffer["confidence"] = incoming_conf
        
        if "metadata_json" in data:
            buffer["metadata_json"].update(data["metadata_json"])
        
        buffer["last_updated"] = now

    def flush_evidence(self, fragment_id: str):
        """[STEP 2] 메모리 버퍼의 데이터를 Evidence Table에 커밋 (Schema 동기화)"""
        data = self.evidence_buffer.get(fragment_id)
        if not data: return
        
        with SessionLocal() as db:
            ev = db.query(EvidenceTable).filter_by(fragment_id=fragment_id).first()
            if not ev:
                ev = EvidenceTable(
                    fragment_id=fragment_id, 
                    source_id=data.get("source_id"),
                    start=data.get("start", 0.0),
                    end=data.get("end", 0.0),
                    time_offset=data.get("start", 0.0)
                )
                db.add(ev)
            
            # 필드별 안전 매핑
            ev.text = data.get("text", ev.text)
            ev.audio_energy = data.get("audio_energy", ev.audio_energy)
            ev.silence = data.get("silence", ev.silence)
            ev.scene_change = data.get("scene_change", ev.scene_change)
            ev.motion_score = data.get("motion_score", ev.motion_score)
            ev.speaker = data.get("speaker", ev.speaker)
            ev.keyframe = data.get("keyframe", ev.keyframe)
            ev.confidence = data.get("confidence", ev.confidence)
            
            # [STEP 2] Fallback Reason 정합성 보완
            incoming_fallback = data.get("fallback_reason")

            # ASR 성공 시 stale asr_* fallback 제거
            if data.get("text") and str(data.get("text")).strip():
                current_fb = ev.fallback_reason or ""
                if (
                    current_fb.startswith("asr_rejected:")
                    or current_fb.startswith("asr_provider_error:")
                    or current_fb == "asr_empty"
                ):
                    ev.fallback_reason = None

            # 일반 fallback 업데이트 (None이 아닐 때만)
            if incoming_fallback is not None:
                ev.fallback_reason = incoming_fallback
            
            # 키프레임 확보 시 pending 해제
            if ev.keyframe and ev.fallback_reason == "keyframe_pending":
                ev.fallback_reason = None
            elif not ev.keyframe and not ev.fallback_reason:
                ev.fallback_reason = "keyframe_pending"

            ev.worker_sources = {**(ev.worker_sources or {}), **data.get("worker_sources", {})}
            ev.metadata_json = {**(ev.metadata_json or {}), **data.get("metadata_json", {})}
            ev.last_updated = datetime.datetime.now()
            
            db.commit()

    def get_evidence_board(self, source_id: str):
        """[STEP 2] 특정 소스의 전체 Evidence Board 조회 (정렬 및 필드 보강)"""
        with SessionLocal() as db:
            # [STEP 2] 시작 시간 순서로 정렬
            evidences = db.query(EvidenceTable).filter_by(source_id=source_id).order_by(EvidenceTable.start).all()
            return [
                {
                    "fragment_id": e.fragment_id,
                    "start": e.start,
                    "end": e.end,
                    "text": e.text,
                    "audio_energy": e.audio_energy,
                    "silence": e.silence,
                    "scene_change": e.scene_change,
                    "motion_score": e.motion_score,
                    "keyframe": e.keyframe,
                    "confidence": e.confidence,
                    "fallback_reason": e.fallback_reason,
                    "worker_sources": e.worker_sources,
                    "metadata": e.metadata_json,
                    "metadata_json": e.metadata_json,
                    "worker_name": (e.worker_sources or {}).get("text") or (e.metadata_json or {}).get("asr_provider") or (e.worker_sources or {}).get("audio_energy") or "unknown",
                    "last_updated": str(e.last_updated)
                } for e in evidences
            ]

    def calculate_coverage(self, source_id: str):
        """[STEP 2] Evidence Coverage 측정 (Overlap 0.5s 고려)"""
        source = self.get_source(source_id)
        if not source or not source.duration: return 0.0
        
        evidences = self.get_evidence_board(source_id)
        if not evidences: return 0.0
        
        total_covered = 0.0
        last_end = 0.0
        for e in evidences:
            start = e["start"]
            end = e["end"]
            
            if end <= last_end: continue
            
            effective_start = max(start, last_end)
            total_covered += (end - effective_start)
            last_end = end
            
        coverage = total_covered / source.duration
        return round(min(1.0, coverage), 4)

    def get_analysis_quality(self, source_id: str):
        """[STEP 2-D-R5] 분석 품질 확인 및 재분석 필요성 판단"""
        with SessionLocal() as db:
            from archive.db_models import EvidenceTable, SemanticFragmentTable, ProposalTable, FragmentTable
            
            evidences = db.query(EvidenceTable).filter_by(source_id=source_id).all()
            sfs = db.query(SemanticFragmentTable).filter_by(source_id=source_id).all()
            proposals = db.query(ProposalTable).filter_by(source_id=source_id).all()
            vfs = db.query(FragmentTable).filter_by(source_id=source_id).all()
            
            # Text Coverage 계산 (text가 있는 row들만 대상)
            text_intervals = sorted([(e.start, e.end) for e in evidences if e.text and e.text.strip()])
            text_covered = 0.0
            last_end = 0.0
            for start, end in text_intervals:
                if end <= last_end: continue
                effective_start = max(start, last_end)
                text_covered += (end - effective_start)
                last_end = end
            
            source = self.get_source(source_id)
            text_coverage_ratio = (text_covered / source.duration) if source and source.duration else 0.0
            
            import yaml, os
            config_path = os.path.join(os.path.dirname(__file__), "..", "ai", "config.yaml")
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                current_provider = (cfg.get("active") or {}).get("asr", "unknown")
                # [R14] read current model_size
                current_model_size = (
                    cfg.get("providers", {})
                       .get("whisper", {})
                       .get("config", {})
                       .get("model_size", "unknown")
                )
            except Exception:
                current_provider = "unknown"
                current_model_size = "unknown"

            stored_providers = set()
            stored_model_sizes = set()  # [R14]
            for e in evidences:
                meta = e.metadata_json or {}
                p = meta.get("asr_provider")
                if p:
                    stored_providers.add(p)
                m = meta.get("asr_model_size")  # [R14]
                if m:
                    stored_model_sizes.add(m)

            # 우선순위 1: OLD_ASR_CONTRACT
            has_old_contract = any(not e.text and e.fallback_reason is None for e in evidences)

            # 우선순위 2: ASR_PROVIDER_CHANGED
            provider_changed = (
                current_provider != "unknown"
                and bool(stored_providers)
                and current_provider not in stored_providers
                and text_coverage_ratio < 0.5
            )

            # 우선순위 3: ASR_MODEL_MISSING
            # whisper 결과는 있지만 model_size 정보가 없는 구버전 결과
            model_missing = (
                current_provider == "whisper"
                and "whisper" in stored_providers
                and not stored_model_sizes
                and text_coverage_ratio > 0   # text가 존재하는 경우에만 (empty는 별도 처리)
            )

            # 우선순위 4: ASR_MODEL_CHANGED
            # model_size 정보가 있고 현재 config와 다른 경우
            model_changed = (
                bool(stored_model_sizes)
                and current_model_size != "unknown"
                and current_model_size not in stored_model_sizes
            )

            # 우선순위 5: ASR_ATTEMPTED_NO_TEXT (same provider/model) → 재분석 금지
            asr_attempted_no_text = (
                not has_old_contract
                and not provider_changed
                and not model_missing
                and not model_changed
                and text_coverage_ratio < 0.5
                and any(
                    (e.fallback_reason or "").startswith("asr_rejected")
                    or (e.fallback_reason or "").startswith("asr_empty")
                    or (e.fallback_reason or "").startswith("asr_provider_error")
                    for e in evidences
                )
            )

            needs_asr = has_old_contract or provider_changed or model_missing or model_changed

            reasons = []
            if has_old_contract:  reasons.append("OLD_ASR_CONTRACT")
            if provider_changed:  reasons.append("ASR_PROVIDER_CHANGED")
            if model_missing:     reasons.append("ASR_MODEL_MISSING")
            if model_changed:     reasons.append("ASR_MODEL_CHANGED")
            if asr_attempted_no_text and not needs_asr:
                reasons.append("ASR_ATTEMPTED_NO_TEXT")

            next_action = (
                "REANALYZE_WITH_CURRENT_ASR_PROVIDER" if (has_old_contract or provider_changed)
                else "REANALYZE_WITH_CURRENT_ASR_MODEL" if (model_missing or model_changed)
                else "REVIEW_ASR_PROVIDER" if asr_attempted_no_text
                else "OK"
            )
            
            return {
                "source_id": source_id,
                "fragment_count": len(vfs),
                "evidence_count": len(evidences),
                "text_rows": len(text_intervals),
                "text_coverage_ratio": round(text_coverage_ratio, 4),
                "semantic_count": len(sfs),
                "proposal_count": len(proposals),
                "needs_asr_reanalysis": needs_asr,
                "needs_semantic_regeneration": needs_asr,
                "needs_proposal_regeneration": needs_asr,
                "reason": reasons,
                "current_provider": current_provider,
                "stored_asr_providers": list(stored_providers),
                "current_model_size": current_model_size,          # [R14]
                "stored_asr_model_sizes": list(stored_model_sizes), # [R14]
                "next_action": next_action
            }

    # ═══════════════════════════════════════════════════════════════════
    #   [STEP 3] Quick Scan / Hypothesis
    # ═══════════════════════════════════════════════════════════════════

    def save_quick_scan(self, source_id: str, data: dict):
        with SessionLocal() as db:
            qs = db.query(QuickScanTable).filter_by(source_id=source_id).first()
            if not qs:
                qs = QuickScanTable(source_id=source_id)
                db.add(qs)
            
            qs.summary = data.get("summary")
            qs.representative_images = data.get("representative_images")
            qs.hypothesis = data.get("hypothesis")
            qs.questions = data.get("questions")
            qs.default_intent_seed = data.get("default_intent_seed")
            qs.evidence_progress = data.get("evidence_progress", 0.0)
            qs.updated_at = datetime.datetime.now()
            db.commit()

    def get_quick_scan(self, source_id: str):
        with SessionLocal() as db:
            qs = db.query(QuickScanTable).filter_by(source_id=source_id).first()
            if not qs: return None
            return {
                "source_id": qs.source_id,
                "summary": qs.summary,
                "representative_images": qs.representative_images,
                "hypothesis": qs.hypothesis,
                "questions": qs.questions,
                "default_intent_seed": qs.default_intent_seed,
                "evidence_progress": qs.evidence_progress,
                "updated_at": str(qs.updated_at)
            }

    # [STEP 4] Semantic Fragment Persistence
    def save_semantic_fragments(self, source_id: str, fragments_list: list):
        """[STEP 4] Semantic Fragments 저장 (기존 데이터 삭제 후 교체)"""
        with SessionLocal() as db:
            from archive.db_models import SemanticFragmentTable
            # 기존 데이터 정리
            db.query(SemanticFragmentTable).filter_by(source_id=source_id).delete()
            
            for f in fragments_list:
                db_f = SemanticFragmentTable(
                    id=f.get("id") or f.get("fragment_id"),
                    fragment_id=f.get("fragment_id"),
                    source_id=source_id,
                    start=f.get("start"),
                    end=f.get("end"),
                    semantic_json=f.get("semantic", {}),
                    structural_json=f.get("structural", {}),
                    continuity_json=f.get("continuity", {}),
                    confidence=f.get("confidence", 1.0),
                    fallback_reason=f.get("fallback_reason")
                )
                db.add(db_f)
            db.commit()

    def get_semantic_fragments(self, source_id: str):
        """[STEP 4] Semantic Fragments 조회"""
        with SessionLocal() as db:
            from archive.db_models import SemanticFragmentTable
            rows = db.query(SemanticFragmentTable).filter_by(source_id=source_id).order_by(SemanticFragmentTable.start).all()
            return [
                {
                    "fragment_id": r.fragment_id,
                    "source_id": r.source_id,
                    "start": r.start,
                    "end": r.end,
                    "semantic": r.semantic_json,
                    "structural": r.structural_json,
                    "continuity": r.continuity_json,
                    "confidence": r.confidence,
                    "fallback_reason": r.fallback_reason
                }
                for r in rows
            ]

    # [STEP 5] User Intent Persistence
    def save_user_intent(self, source_id: str, intent_data: dict):
        """[STEP 5] User Intent 반영 및 저장 (Refinement)"""
        with SessionLocal() as db:
            from archive.db_models import UserIntentTable
            intent = db.query(UserIntentTable).filter_by(source_id=source_id).first()
            if not intent:
                intent = UserIntentTable(source_id=source_id)
                db.add(intent)
            
            intent.must_keep = intent_data.get("must_keep", intent.must_keep or [])
            intent.avoid = intent_data.get("avoid", intent.avoid or [])
            intent.tone = intent_data.get("tone", intent.tone)
            intent.target_length = intent_data.get("target_length", intent.target_length)
            intent.priority_axis = intent_data.get("priority_axis", intent.priority_axis or {})
            intent.updated_at = datetime.datetime.now()
            db.commit()
            return intent

    def get_user_intent(self, source_id: str):
        """[STEP 5] User Intent 조회"""
        with SessionLocal() as db:
            from archive.db_models import UserIntentTable
            intent = db.query(UserIntentTable).filter_by(source_id=source_id).first()
            if not intent: return None
            return {
                "source_id": intent.source_id,
                "must_keep": intent.must_keep,
                "avoid": intent.avoid,
                "tone": intent.tone,
                "target_length": intent.target_length,
                "priority_axis": intent.priority_axis,
                "updated_at": str(intent.updated_at)
            }

    # [STEP 6] Proposal Persistence
    def save_proposals(self, source_id: str, proposals: list):
        """[STEP 6] Proposal (A/B) 저장"""
        with SessionLocal() as db:
            from archive.db_models import ProposalTable
            # 기존 제안 삭제 (덮어쓰기)
            db.query(ProposalTable).filter_by(source_id=source_id).delete()
            
            for p in proposals:
                db_p = ProposalTable(
                    proposal_id=p["proposal_id"],
                    source_id=source_id,
                    mode=p["mode"],
                    sequence=p["sequence"],
                    duration=p["duration"],
                    proposal_reason=p.get("proposal_reason"),
                    confidence=p.get("confidence", 1.0),
                    fallback_reason=p.get("fallback_reason")
                )
                db.add(db_p)
            db.commit()

    def get_proposals(self, source_id: str):
        """[STEP 6] 저장된 모든 제안 조회"""
        with SessionLocal() as db:
            from archive.db_models import ProposalTable
            rows = db.query(ProposalTable).filter_by(source_id=source_id).all()
            return [
                {
                    "proposal_id": r.proposal_id,
                    "mode": r.mode,
                    "sequence": r.sequence,
                    "duration": r.duration,
                    "proposal_reason": r.proposal_reason,
                    "confidence": r.confidence,
                    "fallback_reason": r.fallback_reason
                }
                for r in rows
            ]

    def get_analysis_stage(self, source_id: str) -> str:
        """[STEP 10-I.5.18] Determine current analysis stage from DB state (Restoration helper)"""
        with SessionLocal() as db:
            from archive.db_models import ProposalTable, SemanticFragmentTable, EvidenceTable
            if db.query(ProposalTable).filter_by(source_id=source_id).first():
                return "proposal_generation"
            if db.query(SemanticFragmentTable).filter_by(source_id=source_id).first():
                return "semantic_boundary"
            if db.query(EvidenceTable).filter_by(source_id=source_id).first():
                return "whisper"
            return "initial"

    def get_single_proposal(self, proposal_id: str):
        """[STEP 7] 특정 제안 조회 (변환용)"""
        with SessionLocal() as db:
            from archive.db_models import ProposalTable
            p = db.query(ProposalTable).filter_by(proposal_id=proposal_id).first()
            if not p: return None
            return {
                "proposal_id": p.proposal_id,
                "source_id": p.source_id,
                "mode": p.mode,
                "sequence": p.sequence,
                "duration": p.duration
            }

    # [STEP 7] Export Input Persistence
    def save_export_input(self, data: dict):
        """[STEP 7] Export Input 연동 데이터 저장"""
        with SessionLocal() as db:
            from archive.db_models import ExportInputTable
            # proposal_id 기준 중복 제거 (Upsert)
            db.query(ExportInputTable).filter_by(proposal_id=data["proposal_id"]).delete()
            
            db_exp = ExportInputTable(
                export_id=data["export_id"],
                source_id=data["source_id"],
                proposal_id=data["proposal_id"],
                mode=data["mode"],
                clips=data["clips"],
                total_duration=data["total_duration"],
                status=data.get("status", "EXPORT_INPUT_READY")
            )
            db.add(db_exp)
            db.commit()
            return db_exp

    def get_export_input_by_source(self, source_id: str):
        """[STEP 7] 소스별 Export Input 조회"""
        with SessionLocal() as db:
            from archive.db_models import ExportInputTable
            rows = db.query(ExportInputTable).filter_by(source_id=source_id).all()
            return [self._format_export_input(r) for r in rows]

    def get_export_input_by_proposal(self, proposal_id: str):
        """[STEP 7] 제안별 Export Input 조회"""
        with SessionLocal() as db:
            from archive.db_models import ExportInputTable
            r = db.query(ExportInputTable).filter_by(proposal_id=proposal_id).first()
            return self._format_export_input(r) if r else None

    def _format_export_input(self, r):
        return {
            "export_id": r.export_id,
            "source_id": r.source_id,
            "proposal_id": r.proposal_id,
            "mode": r.mode,
            "clips": r.clips,
            "total_duration": r.total_duration,
            "status": r.status
        }

    # [STEP 8] Render Result Persistence
    def save_render_result(self, data: dict):
        """[STEP 8] Render 결과 저장"""
        with SessionLocal() as db:
            from archive.db_models import ExportResultTable
            # Upsert
            db.query(ExportResultTable).filter_by(export_input_id=data["export_input_id"]).delete()
            
            db_res = ExportResultTable(
                id=data["id"],
                export_input_id=data["export_input_id"],
                proposal_id=data["proposal_id"],
                source_id=data["source_id"],
                output_path_internal=data["output_path_internal"],
                output_url=data["output_url"],
                status=data["status"],
                file_size=data.get("file_size"),
                duration=data.get("duration"),
                codec=data.get("codec"),
                ffmpeg_command_summary=data.get("ffmpeg_command_summary"),
                ffmpeg_stderr=data.get("ffmpeg_stderr")
            )
            db.add(db_res)
            db.commit()
            return db_res

    def get_render_result(self, export_input_id: str):
        """[STEP 8] Render 결과 조회"""
        with SessionLocal() as db:
            from archive.db_models import ExportResultTable
            r = db.query(ExportResultTable).filter_by(export_input_id=export_input_id).first()
            if not r: return None
            return {
                "id": r.id,
                "export_input_id": r.export_input_id,
                "proposal_id": r.proposal_id,
                "source_id": r.source_id,
                "output_url": r.output_url,
                "status": r.status,
                "file_size": r.file_size,
                "duration": r.duration,
                "created_at": str(r.created_at)
            }

bams = BAMSManager()
