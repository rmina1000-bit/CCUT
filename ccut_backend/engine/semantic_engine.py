import datetime
import hashlib
import math
import uuid

from edit_contract.time_units import to_ms


def stable_fragment_key(source_id: str, start_sec: float, end_sec: float,
                        taken: set = None) -> str:
    """[FID-STABLE] 조각 id의 앞자리를 내용 좌표에서 결정론으로 만든다.

    왜: 구판은 `uuid4().hex[:6]` — 내용과 무관한 난수였다. 같은 영상을 다시 분석하면
    경계는 같은데 id만 전부 갈렸고(실측 2026-07-30: SF_EDD33C_… -> SF_E7B3F2_…),
    원고(story.fids)·편집·제안이 죽은 id를 가리켜 조각맵이 통째로 비었다.
    같은 구간이면 같은 이름이어야 한다 — 그래야 다시 분석해도 사용자의 작업이 살아남는다.

    주소는 v0.4 계약의 시간 권위(ms 정수)를 쓴다. 초 부동소수를 그대로 해싱하면
    같은 경계가 실행마다 다른 비트로 보일 수 있다 — 변환은 to_ms 하나뿐(CLAUDE.md).

    형식·길이는 구판과 동일(대문자 6자리 hex). 바깥에서 id를 쪼개 보는 코드
    (`_P001` 접미사, `_c1` 분할, base id 복원)가 그대로 성립한다.

    taken: 같은 실행에서 이미 쓴 앞자리. 충돌하면 결정론적으로 다음 후보를 만든다
    (6자리 hex는 유한하므로 실측 기반 방어 — 조용히 덮어쓰지 않는다).
    """
    base = f"{source_id}|{to_ms(float(start_sec))}|{to_ms(float(end_sec))}"
    attempt = 0
    while True:
        raw = base if attempt == 0 else f"{base}|{attempt}"
        key = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6].upper()
        if taken is None or key not in taken:
            if taken is not None:
                taken.add(key)
            return key
        attempt += 1

def snap_fragment_end_to_sentence(
    fragment_end_sec: float,
    word_timestamps: list,
    max_snap_sec: float = 2.0,
    min_fragment_duration_sec: float = 3.0,
    fragment_start_sec: float = 0.0
) -> tuple:
    """
    fragment end를 가장 가까운 문장 끝점으로 보정한다.

    Returns:
        (adjusted_end_sec: float, snap_applied: bool)
    """
    SENTENCE_END_CHARS = set("。.?!…")
    KOREAN_ENDINGS = ("다", "요", "죠", "네", "까", "나")

    if not word_timestamps:
        return fragment_end_sec, False

    # 문장 끝점 후보 수집
    candidates = []
    for w in word_timestamps:
        word = (w.get("word") or "").strip()
        end = w.get("end")
        if end is None:
            continue
        if word and (
            word[-1] in SENTENCE_END_CHARS
            or word.endswith(KOREAN_ENDINGS)
        ):
            candidates.append(end)

    if not candidates:
        return fragment_end_sec, False

    # fragment_end_sec에 가장 가까운 후보 선택 (max_snap_sec 이내)
    best = None
    best_gap = float("inf")
    for c in candidates:
        gap = abs(fragment_end_sec - c)
        if gap <= max_snap_sec and gap < best_gap:
            best = c
            best_gap = gap

    if best is None:
        return fragment_end_sec, False

    # 보정 후 조각 길이 검증 (최소 길이 보장)
    adjusted = best
    if (adjusted - fragment_start_sec) < min_fragment_duration_sec:
        return fragment_end_sec, False

    return adjusted, True

class SemanticFragmentGenerator:
    """
    [STEP 4] Semantic Fragment Generator (v3.2.1)
    Evidence Board를 의미 단위(Semantic)로 그룹화하고 Role/Value/Continuity를 부여합니다.
    """
    def __init__(self, bams):
        self.bams = bams
        self._snap_debug = {}   # ← 추가

    def generate(self, source_id: str):
        _r16_loaded = True  # proof flag
        # 1. Evidence 조회
        evidences = self.bams.get_evidence_board(source_id)
        if not evidences:
            print(f"[SEMANTIC] No evidence found for {source_id}")
            return []

        import json as _json

        # word_map 구성 (DB 기반 조회)
        word_map = {}
        source_fragments = self.bams.get_fragments_by_source(source_id)
        for vf in source_fragments:
            fid = vf.get("fragment_id")
            intel = vf.get("intelligence") or {}
            if isinstance(intel, str):
                try:
                    intel = _json.loads(intel)
                except Exception:
                    intel = {}
            word_map[fid] = intel

        for ev in evidences:
            fid = ev.get("fragment_id")
            if fid and fid not in word_map:
                intel = ev.get("intelligence") or {}
                if isinstance(intel, str):
                    try:
                        intel = _json.loads(intel)
                    except Exception:
                        intel = {}
                # Fallback if intelligence is missing
                if not intel:
                    intel = {
                        "words": ev.get("words", []),
                        "transcript": ev.get("text", "")
                    }
                word_map[fid] = intel

        # 2. Quick Scan / default_intent_seed 조회
        quick_scan = self.bams.get_quick_scan(source_id)
        intent_seed = quick_scan.get("default_intent_seed") if quick_scan else self._get_default_intent()
        
        source = self.bams.get_source(source_id)
        total_duration = source.duration if (source and source.duration) else (evidences[-1]["end"] if evidences else 0)
        self._current_total_duration = total_duration
        self._current_source_id = source_id

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

        # 8. Merge / Split 보정 (2s ~ 60s) - 스마트 상황 반영을 위해 evidences 전달
        final_fragments = self.apply_merge_split(final_fragments, boundaries, total_duration, evidences=evidences)

        # R16-R1: Sentence Boundary Snap 보정
        final_fragments, snap_debug = self.apply_sentence_boundary_snap(
            final_fragments,
            word_map,
            evidences=evidences,
            total_duration=total_duration
        )
        self._snap_debug = snap_debug   # instance에 보관

        # [STEP 4 RESYNC] 최종 경계 확정 후 fallback_reason 재계산
        for frag in final_fragments:
            frag["fallback_reason"] = self.calculate_fallback_reason(frag)

        # 9. DB 저장
        self.bams.save_semantic_fragments(source_id, final_fragments)
        try:
            from engine.silero_sensor import run_source as run_silero_sensor
            sensor_result = run_silero_sensor(source_id)
            print(f"[SILERO_SENSOR] {sensor_result}", flush=True)
        except Exception as sensor_error:
            print(
                f"[SILERO_SENSOR] source={source_id} non-blocking error: "
                f"{sensor_error}",
                flush=True,
            )

        # [SEMANTIC DIAGNOSTIC] Final summary
        print(f"[SEMANTIC DIAGNOSTIC] Final semantic duration list (first 20): {[round(f['structural']['duration'], 1) for f in final_fragments[:20]]}")
        print(f"{'='*60}\n")

        print(f"[SEMANTIC] {len(final_fragments)} fragments generated for {source_id}")
        return final_fragments

    def apply_sentence_boundary_snap(
        self,
        final_fragments: list,
        word_map: dict,
        evidences: list = None,
        max_snap_sec: float = 2.0,
        min_fragment_duration_sec: float = 3.0,
        total_duration: float = 0.0
    ) -> tuple:
        snap_applied_count = 0
        debug_rows = []

        # Global candidates collection to match the audit exactly
        puncs = ('.', '?', '!', '…', '。')
        korean_endings = ('다', '요', '죠', '네', '까', '나')
        all_endings = puncs + korean_endings

        global_candidates = {}          # snap 허용 후보 (real_words 계열만)
        global_candidates_derived = {}  # diagnostic 전용 (fragment_transcript_end 등)
        global_candidate_details = []

        source_id = final_fragments[0]["source_id"] if final_fragments else None
        if source_id:
            # 1. Fetch fragments
            source_fragments = self.bams.get_fragments_by_source(source_id)
            for vf in source_fragments:
                intel = vf.get("intelligence") or {}
                if isinstance(intel, str):
                    try:
                        import json as _json
                        intel = _json.loads(intel)
                    except Exception:
                        intel = {}
                
                transcript = intel.get("transcript", "") or ""
                words = intel.get("words", []) or []

                if words:
                    current_pos = 0
                    word_spans = []
                    for w in words:
                        w_text = w.get("word", "")
                        if not w_text:
                            continue
                        pos = transcript.find(w_text, current_pos)
                        if pos != -1:
                            word_spans.append({
                                "word": w_text,
                                "start_time": w.get("start"),
                                "end_time": w.get("end"),
                                "start_char": pos,
                                "end_char": pos + len(w_text)
                            })
                            current_pos = pos + len(w_text)
                        else:
                            pos = transcript.find(w_text)
                            if pos != -1:
                                word_spans.append({
                                    "word": w_text,
                                    "start_time": w.get("start"),
                                    "end_time": w.get("end"),
                                    "start_char": pos,
                                    "end_char": pos + len(w_text)
                                })
                                current_pos = pos + len(w_text)

                    if not word_spans:
                        for w in words:
                            w_text = w.get("word", "").strip()
                            t = w.get("end")
                            if t is not None and w_text:
                                is_end = w_text[-1] in all_endings or w_text[-1] in korean_endings
                                if is_end:
                                    rounded = round(t, 2)
                                    if rounded not in global_candidates:
                                        global_candidates[rounded] = t
                                    global_candidate_details.append({
                                        "time": round(t, 3),
                                        "word": w_text,
                                        "source_fragment_id": vf.get("fragment_id") or "",
                                        "source_type": "word_ending",
                                        "reason": "fallback_ending"
                                    })
                    else:
                        for ws in word_spans:
                            w_text = ws["word"].strip()
                            end_char = ws["end_char"]
                            t = ws["end_time"]
                            if t is None:
                                continue

                            is_end = False
                            reason_str = ""
                            source_type = "word_ending"

                            # Condition 1: Word text ends with punctuation or ending
                            if w_text and w_text[-1] in all_endings:
                                is_end = True
                                reason_str = "word_ends_with_ending"
                                source_type = "word_ending"

                            # Condition 2: Followed by punctuation in transcript
                            if not is_end:
                                lookahead = transcript[end_char:end_char+5].strip()
                                if lookahead and lookahead[0] in puncs:
                                    is_end = True
                                    reason_str = "followed_by_punctuation"
                                    source_type = "followed_by_punctuation"

                            # Condition 3: Word text ends with Korean ending
                            if not is_end:
                                if w_text and w_text[-1] in korean_endings:
                                    is_end = True
                                    reason_str = "word_ends_with_korean_ending"
                                    source_type = "word_ending"

                            if is_end:
                                rounded = round(t, 2)
                                if rounded not in global_candidates:
                                    global_candidates[rounded] = t
                                global_candidate_details.append({
                                    "time": round(t, 3),
                                    "word": w_text,
                                    "source_fragment_id": vf.get("fragment_id") or "",
                                    "source_type": source_type,
                                    "reason": reason_str
                                })

                # B. Fragment transcript end
                if transcript:
                    transcript_stripped = transcript.strip()
                    if transcript_stripped and transcript_stripped[-1] in all_endings:
                        t = vf.get("end_time")
                        if t is not None:
                            rounded = round(t, 2)
                            if rounded not in global_candidates_derived:
                                global_candidates_derived[rounded] = t
                            global_candidate_details.append({
                                "time": round(t, 3),
                                "word": transcript_stripped[-20:],
                                "source_fragment_id": vf.get("fragment_id") or "",
                                "source_type": "fragment_transcript_end",
                                "reason": "fragment_transcript_end"
                            })

            # 2. Fetch evidence board text ends
            if evidences:
                for ev in evidences:
                    text = ev.get("text")
                    if text:
                        text_stripped = text.strip()
                        if text_stripped and text_stripped[-1] in all_endings:
                            t = ev.get("end")
                            if t is not None:
                                rounded = round(t, 2)
                                if rounded not in global_candidates_derived:
                                    global_candidates_derived[rounded] = t
                                global_candidate_details.append({
                                    "time": round(t, 3),
                                    "word": text_stripped[-20:],
                                    "source_fragment_id": ev.get("fragment_id") or "",
                                    "source_type": "evidence_board_text_end",
                                    "reason": "evidence_board_text_end"
                                })

        # [OPTIMIZATION] O(E) 탐색 방지를 위한 evidence hash map 구축
        evidence_map = {ev.get("fragment_id"): ev for ev in evidences if ev.get("fragment_id")} if evidences else {}

        for i, frag in enumerate(final_fragments):
            # 이 fragment에 해당하는 words 수집 (real_words count 용)
            words = []
            for ref in frag.get("semantic", {}).get("evidence_refs", []):
                intel = word_map.get(ref, {})
                words.extend(intel.get("words", []) or [])
            words.sort(key=lambda x: x.get("start", 0.0))

            # evidence text fallback: text를 공백 분리 후 마지막 단어들을 word 후보로 추가 (debug only)
            ev_words = []
            if evidences:
                for ref in frag.get("semantic", {}).get("evidence_refs", []):
                    ev = evidence_map.get(ref)
                    if ev and ev.get("text"):
                        text = ev["text"].strip()
                        tokens = text.split()
                        # 각 토큰을 가상 word timestamp로 변환
                        # start/end를 fragment 구간에 균등 분배 (근사값)
                        if tokens:
                            frag_dur = frag["end"] - frag["start"]
                            step = frag_dur / len(tokens)
                            for j, tok in enumerate(tokens):
                                ev_words.append({
                                    "word": tok,
                                    "start": round(frag["start"] + j * step, 3),
                                    "end": round(frag["start"] + (j + 1) * step, 3)
                                })

            # real_words 기반으로 이 fragment에 속한 sentence end 후보 계산
            curr_candidates = []
            for ref in frag.get("semantic", {}).get("evidence_refs", []):
                intel = word_map.get(ref, {})
                ref_words = intel.get("words", []) or []
                transcript = intel.get("transcript", "") or ""

                if ref_words:
                    current_pos = 0
                    word_spans = []
                    for w in ref_words:
                        w_text = w.get("word", "")
                        if not w_text:
                            continue
                        pos = transcript.find(w_text, current_pos)
                        if pos != -1:
                            word_spans.append({
                                "word": w_text,
                                "start_time": w.get("start"),
                                "end_time": w.get("end"),
                                "start_char": pos,
                                "end_char": pos + len(w_text)
                            })
                            current_pos = pos + len(w_text)
                        else:
                            pos = transcript.find(w_text)
                            if pos != -1:
                                word_spans.append({
                                    "word": w_text,
                                    "start_time": w.get("start"),
                                    "end_time": w.get("end"),
                                    "start_char": pos,
                                    "end_char": pos + len(w_text)
                                })
                                current_pos = pos + len(w_text)

                    if not word_spans:
                        for w in ref_words:
                            w_text = w.get("word", "").strip()
                            t = w.get("end")
                            if t is not None and w_text:
                                is_end = w_text[-1] in all_endings or w_text[-1] in korean_endings
                                if is_end:
                                    curr_candidates.append(t)
                    else:
                        for ws in word_spans:
                            w_text = ws["word"].strip()
                            end_char = ws["end_char"]
                            t = ws["end_time"]
                            if t is None:
                                continue

                            is_end = False
                            if w_text and w_text[-1] in all_endings:
                                is_end = True
                            if not is_end:
                                lookahead = transcript[end_char:end_char+5].strip()
                                if lookahead and lookahead[0] in puncs:
                                    is_end = True
                            if not is_end:
                                if w_text and w_text[-1] in korean_endings:
                                    is_end = True

                            if is_end:
                                curr_candidates.append(t)

            # snap 후보 입력 용: global_candidates를 dict 형식의 리스트로 가공
            snap_input_candidates = [{"word": ".", "end": t} for t in global_candidates.values()]

            # snap 후보 계산 (global candidates 기반)
            adjusted_end, snap_applied = snap_fragment_end_to_sentence(
                fragment_end_sec=frag["end"],
                word_timestamps=snap_input_candidates,
                max_snap_sec=max_snap_sec,
                min_fragment_duration_sec=min_fragment_duration_sec,
                fragment_start_sec=frag["start"]
            )

            # audit과 동일한 방식으로 nearest_candidate, gap_sec 계산 (global candidates 기반)
            nearest_candidate = None
            gap_sec = None
            if global_candidates:
                nearest_candidate = min(global_candidates.values(), key=lambda c: abs(frag["end"] - c))
                nearest_candidate = round(nearest_candidate, 3)
                gap_sec = round(abs(frag["end"] - nearest_candidate), 4)

            candidate_source = "real_words" if words else "none"
            actual_delta_sec = round(abs(adjusted_end - frag["end"]), 4)

            row = {
                "fragment_id": frag["fragment_id"],
                "old_end": frag["end"],
                "adjusted_end": adjusted_end if snap_applied else frag["end"],
                "actual_delta_sec": actual_delta_sec if snap_applied else 0.0,
                "word_count": len(words),                  # 실제 Whisper words 수
                "ev_word_count": len(ev_words),            # evidence text 가상 토큰 수 (debug only)
                "candidate_count": len(curr_candidates),   # 이 fragment에 속하는 real_words 기반 sentence end 후보 수
                "candidate_source": candidate_source,
                "nearest_candidate": nearest_candidate,
                "gap_sec": gap_sec,
                "snap_applied": snap_applied,
                "skip_reason": None
            }

            print(f"[SNAP] frag={frag['fragment_id'][:30]} word_count={len(words)} ev_word_count={len(ev_words)} global_candidates={len(global_candidates)}")

            if snap_applied:
                if actual_delta_sec < 0.05:
                    snap_applied = False
                    row["snap_applied"] = False
                    row["adjusted_end"] = frag["end"]
                    row["actual_delta_sec"] = 0.0
                    row["skip_reason"] = "NO_OP_SAME_END"
                elif candidate_source != "real_words":
                    snap_applied = False
                    row["snap_applied"] = False
                    row["adjusted_end"] = frag["end"]
                    row["actual_delta_sec"] = 0.0
                    row["skip_reason"] = "NOT_REAL_WORDS"

            old_end = frag["end"]

            if not snap_applied:
                if not row["skip_reason"]:
                    if row["gap_sec"] is not None and row["gap_sec"] > max_snap_sec:
                        row["skip_reason"] = "GAP_EXCEEDS_MAX_SNAP"
                    elif row["candidate_count"] == 0:
                        # candidate_count가 0이더라도 global_candidate와 매칭될 순 있으나 skip 사유 처리를 위해 설정
                        row["skip_reason"] = "NO_CANDIDATE"
                    else:
                        # 가드 조건 판단
                        next_frag = final_fragments[i + 1] if i + 1 < len(final_fragments) else None
                        if next_frag is not None:
                            if next_frag["end"] - adjusted_end < min_fragment_duration_sec:
                                row["skip_reason"] = "NEXT_FRAGMENT_TOO_SHORT"
                            else:
                                row["skip_reason"] = "SNAP_FUNC_INTERNAL_GUARD"
                        else:
                            if total_duration > 0 and adjusted_end > total_duration:
                                row["skip_reason"] = "EXCEEDS_TOTAL_DURATION"
                            else:
                                row["skip_reason"] = "SNAP_FUNC_INTERNAL_GUARD"
                print(f"[SNAP] SKIPPED: {frag['fragment_id'][:30]} end={frag['end']:.2f} (reason={row['skip_reason']})")
            else:
                next_frag = final_fragments[i + 1] if i + 1 < len(final_fragments) else None

                # 안전 조건 검사
                if next_frag is not None:
                    # 다음 fragment duration이 3초 미만이 되면 snap 금지
                    if next_frag["end"] - adjusted_end < min_fragment_duration_sec:
                        row["skip_reason"] = "NEXT_FRAGMENT_TOO_SHORT"
                        row["snap_applied"] = False
                        row["adjusted_end"] = frag["end"]
                        row["actual_delta_sec"] = 0.0
                        print(f"[SNAP] SKIPPED: {frag['fragment_id'][:30]} end={frag['end']:.2f} (next duration guard)")
                        debug_rows.append(row)
                        continue
                else:
                    # 마지막 fragment: total_duration 초과 금지
                    if total_duration > 0 and adjusted_end > total_duration:
                        row["skip_reason"] = "EXCEEDS_TOTAL_DURATION"
                        row["snap_applied"] = False
                        row["adjusted_end"] = frag["end"]
                        row["actual_delta_sec"] = 0.0
                        print(f"[SNAP] SKIPPED: {frag['fragment_id'][:30]} end={frag['end']:.2f} (total duration guard)")
                        debug_rows.append(row)
                        continue

                # 적용
                frag["end"] = adjusted_end
                frag["structural"]["duration"] = round(adjusted_end - frag["start"], 2)

                # 연쇄 정합성: 다음 fragment start도 맞춤
                if next_frag is not None:
                    next_frag["start"] = adjusted_end
                    next_frag["structural"]["duration"] = round(next_frag["end"] - next_frag["start"], 2)

                snap_applied_count += 1
                row["snap_applied"] = True
                row["adjusted_end"] = adjusted_end
                row["actual_delta_sec"] = actual_delta_sec
                print(f"[SNAP] APPLIED: {frag['fragment_id'][:30]} end {old_end:.2f} → {adjusted_end:.2f}")

            debug_rows.append(row)

        # 32.0~34.5초 구간 global candidate details만 추출해서 snap_debug에 포함
        global_candidates_32_34 = [
            d for d in global_candidate_details
            if 32.0 <= d["time"] <= 34.5
        ]
        global_candidates_32_34.sort(key=lambda x: x["time"])

        debug_info = {
            "r16_loaded": True,
            "called": True,
            "snap_applied_count": snap_applied_count,
            "real_word_candidate_count": len(global_candidates),
            "derived_candidate_count": len(global_candidates_derived),
            "global_candidates_32_34": global_candidates_32_34,   # ← detail 포함
            "rows": debug_rows
        }

        print(f"[SNAP] snap_applied_count: {snap_applied_count}")
        for row in debug_rows:
            print(f"[SNAP] {row}")

        return final_fragments, debug_info

    def create_fragment_boundaries(self, evidences, total_duration=0):
        """
        [STEP 10-I.5.3] Text-first 경계 후보 생성
        - whisper_segments: 가장 강력한 텍스트/문장 경계
        - scene_change: 시각적 전환
        - silence: 오디오 중단
        - VF artificial boundaries (30s)는 의도적으로 제외
        """
        boundaries = [0.0]
        
        # 1. Text-based Segments (Text-first priority)
        text_evs = []
        for ev in evidences:
            is_text_evidence = (
                bool(ev.get("text")) and (
                    ev.get("worker_name") in ["whisper", "qwen3_asr", "asr", "whisper_segments"]
                    or (ev.get("worker_sources") or {}).get("text") in ["whisper", "qwen3_asr", "asr", "whisper_segments"]
                    or (ev.get("metadata_json") or {}).get("asr_provider")
                )
            )
            if is_text_evidence:
                text_evs.append(ev)
                boundaries.append(ev["start"])
                boundaries.append(ev["end"])

        # 2. Scene Changes & Silence from all evidences
        for ev in evidences:
            wn = ev.get("worker_name", "unknown")
            # [STEP 10-I.5.9] Skip boundaries from workers that just repeat VF boundaries
            # [단계3] 텍스트가 없는 evidence의 scene_change는 스킵 면제.
            # ASR worker 중복 방지는 텍스트가 실제로 있을 때만 적용.
            # text 키가 None으로 실존하는 evidence(무발화/ASR 스킵 소스)에서 죽지 않는다 — None=빈 문자열 동등
            has_text = bool((ev.get("text") or "").strip())
            if has_text and wn in ["audio", "signal_processor", "whisper", "qwen3_asr", "asr"]:
                continue

            if ev.get("scene_change") and isinstance(ev["scene_change"], list):
                for ts in ev["scene_change"]:
                    boundaries.append(ts)
            
            # Silence detection (usually from specialized silence detectors)
            if wn == "silence" or ev.get("audio_energy", 1.0) < 0.05:
                boundaries.append(ev["start"])

        # [STEP 10-I.5.9] Boundary source distribution log
        text_boundary_count = len(text_evs) * 2
        scene_boundary_count = sum(len(ev["scene_change"]) for ev in evidences if ev.get("scene_change") and isinstance(ev["scene_change"], list))
        silence_boundary_count = sum(1 for ev in evidences if (ev.get("worker_name") == "silence" or (ev.get("audio_energy", 1.0) < 0.05 and ev.get("worker_name") not in ["audio", "signal_processor", "whisper", "qwen3_asr", "asr"])))
        
        print(f"[SEMANTIC DIAGNOSTIC] Boundary distribution:")
        print(f"  - text/asr segments: {text_boundary_count}")
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
        
        # [단계3.5] 경계 후보 밀도 적응 간격.
        # 후보가 4초당 1개를 넘는 과밀 상태면 간격을 2.5초로 넓혀
        # scene threshold 과발화로 인한 과분쇄를 방지한다.
        _density = (len(sorted_b) / total_duration) if total_duration > 0 else 0.0
        _min_gap = 0.8 if _density <= 0.25 else 2.5
        print(f"[SEMANTIC DIAGNOSTIC] boundary density={_density:.3f}/s -> min_gap={_min_gap}s")
        filtered = [sorted_b[0]]
        for b in sorted_b[1:]:
            if b - filtered[-1] >= _min_gap:
                filtered.append(b)
        
        # 마지막 경계가 total_duration보다 작으면 추가 (전체 영상 커버 보장)
        # 만약 filtered의 길이가 2 미만이면 강제로 total_duration (또는 evidences의 최대 end)을 추가하여 최소 1개의 fragment가 생성되도록 보장
        target_end = total_duration if total_duration > 0 else (max([e["end"] for e in evidences]) if evidences else 0.0)
        if len(filtered) < 2 and target_end > 0.0:
            filtered.append(target_end)
        elif target_end > 0.0 and filtered[-1] < target_end - 0.5:
            filtered.append(target_end)
             
        # [단계3.6] 경계 기근 감지: 평균 조각 길이 25초 초과 시 보강
        _avg_len = (total_duration / max(len(filtered) - 1, 1)) if total_duration > 0 else 0
        if total_duration > 0 and _avg_len > 25.0:
            print(f"[BOUNDARY_RESCUE] 기근 감지 (avg={_avg_len:.1f}s) - 보강 시작")
            _added = []

            # (B) 저임계 장면 재스캔
            _src = self.bams.get_source(getattr(self, '_current_source_id', None) or '')
            _fp = getattr(_src, 'file_path', None) if _src else None
            if _fp:
                from engine.signal_processor import detect_scenes_rescan
                _rescan = detect_scenes_rescan(_fp, total_duration)
                print(f"[BOUNDARY_RESCUE] 저임계 재스캔 후보: {len(_rescan)}개")
                _added.extend(_rescan)

            # (B2) [M-2] 모션 변곡점 — 점진 변화 영상용
            # (저임계 재스캔 0개일 때. 컷 없는 원테이크의 내용 경계)
            if not _added:
                from engine.signal_processor import (
                    extract_motion_curve,
                    find_motion_inflections,
                )
                import os as _os2
                _sid = getattr(self, '_current_source_id', '') or ''
                # [M-2.2] proxy 위치는 원본 위치와 무관하게
                # 레포 루트의 storage/proxies 고정 —
                # 코드 위치(__file__) 앵커로 CWD·원본경로 모두 독립.
                _repo_root = _os2.path.dirname(_os2.path.dirname(
                    _os2.path.dirname(_os2.path.abspath(__file__))))
                _proxy = _os2.path.join(
                    _repo_root, "storage", "proxies",
                    f"{_sid}_proxy.mp4")
                _mpath = _proxy if _os2.path.exists(_proxy) else _fp
                if _mpath:
                    _curve = extract_motion_curve(_mpath, total_duration)
                    _infl = find_motion_inflections(_curve)
                    print(f"[BOUNDARY_RESCUE] 모션 변곡점: "
                          f"후보 {len(_infl)}개 "
                          f"(curve {len(_curve)} samples)")
                    _added.extend([c["t"] for c in _infl])

            # (C) VF 물리 경계 폴백 (VF 접두사 필수 — fragments 테이블 오염 방어)
            if not _added:
                _vf_pts = []
                for _ev in evidences:
                    _fid = _ev.get("fragment_id", "")
                    if _fid.startswith("VF"):
                        _vf_pts.extend([_ev["start"], _ev["end"]])
                print(f"[BOUNDARY_RESCUE] VF 경계 폴백: {len(_vf_pts)}개")
                _added.extend(_vf_pts)

            if _added:
                _all = sorted(set(
                    [round(b, 2) for b in (filtered + _added)]
                ))
                # 기존 밀도 적응 간격 재적용
                _d2 = len(_all) / max(total_duration, 1.0)
                _g2 = 0.8 if _d2 <= 0.25 else 2.5
                _ref = [_all[0]]
                for _b in _all[1:]:
                    if _b - _ref[-1] >= _g2:
                        _ref.append(_b)
                if _ref[-1] < total_duration - 0.5:
                    _ref.append(total_duration)
                filtered = _ref
                print(f"[BOUNDARY_RESCUE] 보강 후 boundary {len(filtered)}개")

        return filtered

    def build_fragments(self, source_id, evidences, boundaries):
        """[STEP 10-I.5.3] Global boundaries 기반으로 조각 생성 (30s 경계 무관)"""
        import json as _json
        final_fragments = []
        raw_vf_fragments = self.bams.get_fragments_by_source(source_id)
        # [FID-STABLE] 이 실행에서 이미 쓴 앞자리 — 6자리 hex 충돌 시 결정론적으로 비켜간다.
        taken_keys = set()

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

            # raw VF 조각 intelligence(silence_ratio/motion_blur) 시간 중첩 매칭
            overlapping_vfs = [
                vf for vf in raw_vf_fragments
                if not (vf.get("end_time", 0) <= start or vf.get("start_time", 0) >= end)
            ]
            primary_vf_intel = overlapping_vfs[0].get("intelligence") if overlapping_vfs else {}
            if isinstance(primary_vf_intel, str):
                try:
                    primary_vf_intel = _json.loads(primary_vf_intel)
                except Exception:
                    primary_vf_intel = {}
            if not isinstance(primary_vf_intel, dict):
                primary_vf_intel = {}

            # [FID-STABLE] 난수 uuid4 폐기 — 같은 구간이면 같은 이름.
            #   구판: f"SF_{uuid.uuid4().hex[:6].upper()}_{source_id}"
            sf_id = f"SF_{stable_fragment_key(source_id, start, end, taken_keys)}_{source_id}"
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
                    "duration": duration,
                    "silence_ratio": primary_vf_intel.get("silence_ratio", 0.0),
                    "motion_blur": primary_vf_intel.get("motion_blur", 1.0)
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
        if not ref_evs:
            # [B-2] motion/audio 기반 fallback 계산 (evidence_refs 매칭 실패 시)
            if all_evidences:
                _avg_motion = sum(e.get("motion_score", 0.0) or 0.0 for e in all_evidences) / len(all_evidences)
                _avg_audio = sum(e.get("audio_energy", 0.0) or 0.0 for e in all_evidences) / len(all_evidences)
                _text_bonus = 0.1 if any(e.get("text") for e in all_evidences) else 0.0
                return round(max(0.1, min(0.9, 0.3 + _avg_motion * 0.3 + _avg_audio * 0.3 + _text_bonus)), 4)
            return 0.3
        
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
        # [B-1] sentiment_continuity 실계산 (텍스트 유무 + confidence 기반)
        _has_text = bool(
            current.get("text") or
            current.get("semantic", {}).get("transcript_refs")
        )
        _conf = current.get("confidence", 0.5) or 0.5
        if _has_text and _conf >= 0.8:
            sentiment_continuity = 1.0
        elif _has_text:
            sentiment_continuity = 0.7
        else:
            sentiment_continuity = 0.3

        continuity = {
            "topic_similarity": 0.5, "time_proximity": 1.0,
            "sentiment_continuity": sentiment_continuity, "narrative_flow": 0.5
        }
        if prev:
            gap = current["start"] - prev["end"]
            continuity["time_proximity"] = max(0.0, 1.0 - (abs(gap) / 2.0))
            continuity["topic_similarity"] = 0.7 if current["semantic"]["topic"] == prev["semantic"]["topic"] else 0.4
        return continuity

    def _is_important_boundary(self, boundary_time: float, evidences: list) -> bool:
        """
        [CONTEXT_AWARE_BOUNDARY] 경계 시간대(boundary_time)가 장면 전환이나 오디오/문장의 시작/끝이 있는 중요 지점인지 판별합니다.
        """
        if not evidences:
            return False

        for ev in evidences:
            # 1. 장면 전환(Scene Change) 감지
            scene_changes = ev.get("scene_change") or []
            if isinstance(scene_changes, list):
                for sc in scene_changes:
                    if abs(sc - boundary_time) < 0.15:
                        return True

            # 2. Whisper ASR 문장 경계 감지
            if ev.get("worker_name") == "whisper_segments":
                start_t = ev.get("start")
                end_t = ev.get("end")
                if (start_t is not None and abs(start_t - boundary_time) < 0.15) or (end_t is not None and abs(end_t - boundary_time) < 0.15):
                    return True

        return False

    def apply_merge_split(self, fragments, boundaries, total_duration, evidences=None):
        """[STEP 10-I.5.3] Merge (3s 미만) 및 Split (20s 초과) 보정 - 스마트 상황 반영"""
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
            last_dur = last["structural"]["duration"]
            boundary_t = last["end"]
            
            # 중요 경계(장면 전환 또는 문장 전환점)가 존재하는지 확인
            is_important = self._is_important_boundary(boundary_t, evidences) if evidences else False
            
            # 1.5초 미만의 극단적으로 짧은 쓰레기 조각은 흐름을 위해 강제 병합하되,
            # 그 이상(1.5s ~ 3.0s)이면서 중요한 장면 전환/문장이 걸쳐 있으면 병합하지 않고 미세 조각으로 보존
            should_merge = False
            if last_dur < 1.5:
                should_merge = True
            elif last_dur < merge_threshold and not is_important:
                should_merge = True
                
            if should_merge:
                # 병합
                last["end"] = frag["end"]
                last["structural"]["duration"] = round(last["end"] - last["start"], 2)
                for key in ["evidence_refs", "transcript_refs"]:
                    last["semantic"][key] = list(set(last["semantic"][key] + frag["semantic"][key]))
                res[-1] = last
            else:
                res.append(frag)
        
        # [단계3.5] 조각 수 상한 일반화.
        # 짧은 영상(<=60s)은 기존 18개 유지, 긴 영상은 길이 비례
        # (평균 8초/조각 목표, 12~30개 범위로 클램프).
        max_frags = 18 if is_fast_path else max(12, min(30, int(total_duration / 8.0)))
        if len(res) > max_frags:
            print(f"[SEMANTIC] Fragment Limit: {len(res)} -> {max_frags} merging...")
            while len(res) > max_frags:
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
        # [STEP 1-R3] _S1/_S2 재귀 suffix 오염 제거 → _split_long_fragment() 위임
        final = []
        for frag in res:
            if frag["structural"]["duration"] > 20.0:
                final.extend(self._split_long_fragment(frag, boundaries, evidences=evidences))
            else:
                final.append(frag)

        return final

    def _split_long_fragment(self, frag, boundaries, max_duration=20.0, evidences=None):
        """[STEP 1-R3] 긴 조각을 _P001/_P002 형식으로 안정 분할.
        _S1/_S2 suffix 재귀 누적 없음. depth limit 불필요.
        기존 _S1/_S2 suffix가 붙어있으면 제거 후 base_id 사용."""
        start = frag["start"]
        end = frag["end"]

        # 기존 _S1/_S2 오염 suffix 제거하여 clean base_id 확보
        base_id = frag["fragment_id"]
        while base_id.endswith("_S1") or base_id.endswith("_S2"):
            base_id = base_id[:-3]

        parts = []
        cursor = start
        index = 1

        while cursor < end - 0.5:
            # 현재 cursor부터 max_duration 이내 경계 중 구간 중앙에 가장 가까운 것 선택
            seg_end_limit = min(cursor + max_duration, end)
            mid = cursor + (seg_end_limit - cursor) / 2.0
            candidates = [b for b in boundaries if cursor + 5.0 < b < seg_end_limit - 5.0]

            if candidates:
                part_end = sorted(candidates, key=lambda x: abs(x - mid))[0]
            else:
                # [단계3.6.1] 인지 경계 없는 강제 분할은 잔여 구간을
                # 균등 분할한다 (20+9.5 같은 비대칭 꼬리 방지).
                import math as _math
                _remaining = end - cursor
                _n_parts = max(1, _math.ceil(_remaining / max_duration))
                part_end = round(cursor + (_remaining / _n_parts), 2)
                # [단계3.6] 인지 경계 없는 시간 분할 — 정직 기록
                frag.setdefault("semantic", {})["forced_time_split"] = True

            # 마지막 조각이 3초 미만이면 현재 파트에 흡수
            if end - part_end < 3.0:
                part_end = end

            part_end = min(round(part_end, 2), end)
            part_duration = round(part_end - cursor, 2)
            if part_duration < 0.2:
                cursor = part_end
                continue

            child = dict(frag)
            child["semantic"] = dict(frag["semantic"])
            child["continuity"] = dict(frag.get("continuity", {}))
            child["fragment_id"] = f"{base_id}_P{index:03d}"
            child["start"] = round(cursor, 2)
            child["end"] = part_end
            # [단계3] structural 복제 금지 — 자식별 재계산.
            # role/edit_value/market_value는 부모에서 복사하지 않는다.
            child["structural"] = {
                "role": "context",          # 임시값; 아래에서 재계산
                "edit_value": 0.5,          # 임시값; 아래에서 재계산
                "market_value": 0.5,        # 임시값; 아래에서 재계산
                "duration": part_duration,
            }
            # 자식의 실제 start_ratio로 role 재분류
            _total_dur = getattr(self, '_current_total_duration', frag.get("end", part_end))
            _pos = round(cursor, 2) / max(_total_dur, 1.0)
            _edit_v = frag["structural"].get("edit_value", 0.5)
            if _pos < 0.2 and _edit_v >= 0.6:
                child["structural"]["role"] = "hook"
            elif _pos > 0.85:
                child["structural"]["role"] = "closing"
            elif _pos > 0.55 and _edit_v >= 0.55:
                child["structural"]["role"] = "payoff"
            else:
                child["structural"]["role"] = "context"
            child["structural"]["edit_value"] = round(
                _edit_v * (part_duration / max(frag.get("structural", {}).get("duration", part_duration), 0.1)),
                4,
            )
            child["structural"]["market_value"] = child["structural"]["edit_value"]

            # Time range ref re-filtering
            c_start = child["start"]
            c_end = child["end"]
            child_refs = []
            if "evidence_refs" in frag["semantic"] and evidences:
                # Find matching evidence_refs based on time bounds
                child_refs = [
                    ref for ref in frag["semantic"]["evidence_refs"]
                    if any(
                        e["fragment_id"] == ref and not (e["end"] <= c_start or e["start"] >= c_end)
                        for e in evidences
                    )
                ]
            
            child["semantic"]["evidence_refs"] = child_refs
            child["semantic"]["transcript_refs"] = child_refs

            parts.append(child)
            cursor = part_end
            index += 1

            if part_end >= end:
                break

        return parts if parts else [frag]

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
    #   [B-3-FIX] Existing Fragment Reanalysis
    # ═══════════════════════════════════════════════════════════════════

    def reanalyze_existing_fragments(self, source_id: str) -> int:
        """
        [B-3-FIX] 기존 SF_ fragment의 continuity/fallback_reason
        신규 로직으로 일괄 재계산.
        DB를 직접 업데이트하며 sem_gen.generate() 우회.
        """
        fragments = self.bams.get_semantic_fragments(source_id)
        if not fragments:
            print(f"[B-3-FIX] {source_id}: semantic_fragments 없음")
            return 0

        all_evidences = self.bams.get_evidence_board(source_id) or []
        updated = 0
        final_fragments = []
        for frag in fragments:
            prev_frag = final_fragments[-1] if final_fragments else None
            frag["continuity"] = self.calculate_continuity(frag, prev_frag)
            frag["confidence"] = self.calculate_confidence(frag)
            frag["fallback_reason"] = self.calculate_fallback_reason(frag)
            evidence_refs = frag.get("semantic", {}).get("evidence_refs", [])
            frag["structural"]["edit_value"] = self.calculate_edit_value(
                evidence_refs, all_evidences, {}
            )
            final_fragments.append(frag)
            updated += 1

        self.bams.save_semantic_fragments(source_id, final_fragments)
        print(f"[B-3-FIX] {source_id}: {updated}개 재계산 완료")
        return updated

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

        # R-cost: 리듬 비용
        r_cost = 0.0
        duration = fragment.get("structural", {}).get("duration", 0)
        if duration > 0:
            if duration < 3:
                r_cost -= 0.15
            elif 8 <= duration <= 45:
                r_cost += 0.10
            elif duration > 120:
                r_cost -= 0.10

        # Quality-cost: 무음비율/카메라흔들림 비용
        quality_cost = 0.0
        _silence = fragment.get("structural", {}).get("silence_ratio", None)
        if _silence is not None:
            if _silence >= 0.3:
                quality_cost += 0.08
            elif _silence < 0.05:
                quality_cost -= 0.05
        _blur = fragment.get("structural", {}).get("motion_blur", None)
        if _blur is not None:
            if _blur < 0.3:
                quality_cost -= 0.12
            elif _blur >= 0.7:
                quality_cost += 0.05

        # 4. 종합 및 Clamp (User 전용 점수 갱신)
        final_value = base_user_value + must_keep_bonus + avoid_penalty + tone_bonus + r_cost + quality_cost
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
