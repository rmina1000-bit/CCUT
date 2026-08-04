"""[ASR-REPORT 2026-08-01] 첫 신고 장치 — ASR 반복 루프를 원장에 신고한다.

왜 만드는가: SRC_3111FA4F 는 전사의 84.2%가 반복 루프로 소실돼 있었는데
아무도 몰랐다. 코드는 계속 돌았고, 화면은 조용했고, 원인 규명에 스물두 시간이
걸렸다. 시작은 국장이 전사를 읽다 "뇌살리수"가 이상해서 물은 것이었다.

이 장치는 **고치지 않는다. 막지도 않는다. 신고만 한다.**
-mc 0(93c4863e) 반영 후에도 잔여 8.9%가 남는다. 그 잔여가 원장에 쌓여야
다음 처방의 재료가 된다. 지금 넣지 않으면 또 손으로 재야 한다.

반드시 참인 것 하나: **신고 장치는 본선을 막지 않는다.**
ASR 출력이 이상해도 ASR 은 계속 돌고 조각도 만들어진다. 원장에 한 줄 남을 뿐이다.
다만 신고 자체가 실패하면 그건 **드러난다** — 조용히 삼키지 않는다(절벽 ②).

판정기를 새로 만들지 않는다:
  rough_cut.transcript_reader.detect_repetition_hallucination 을 그대로 쓴다.
  07-31 실측 검증 완료 — '노을이 x12' 검출, '뇌살이 두 개 썼는데 x9' 검출(coverage 0.973),
  'LM Studio x3'(정상 언급) 통과. 1,785개 중 5개만 걸렸다.
  두 벌이 되면 같은 지표를 다르게 세게 되고, 그때 12배 오차가 난다(LAB-44 실측).
  임계값도 그 모듈의 것을 그대로 쓴다 — 여기서 새로 잡으면 근거 없는 감이 된다.

신고 단위 = **소스마다 1행 + detail 에 조각 목록** (하이브리드):
  원장에 물어볼 질문은 '얼마나 자주 · 언제부터 · 어떤 상황에서'다.
  조각마다 1행(=47행)이면 한 사건이 47행으로 부풀어 "이번이 세 번째인가"를
  셀 수 없게 된다 — 빈도를 묻는 원장에서 그건 치명적이다.
  반대로 1행만 남기면 해상도가 사라지므로, 영향 조각의 시각·unit·repeat·coverage 를
  detail 에 통째로 담는다. 행은 사건 단위, 해상도는 detail 에.

과거 데이터는 소급 기록하지 않는다(절벽 ④) — 다음 분석부터 쌓인다.
"""
import os
import traceback
from typing import Any, Optional

DOMAIN = "asr"
ERROR_CODE = "repetition_loop"

# detail 에 담는 조각 목록 상한. 잘라도 total_flagged 로 전체 규모는 남는다
# (조용한 절단 금지 — truncated 플래그로 잘렸다는 사실 자체를 적는다).
_DETAIL_MAX_ITEMS = 60


def enabled() -> bool:
    return os.getenv("CCUT_ASR_REPETITION_REPORT", "1") in ("1", "true", "True")


def scan(fragment_transcripts: dict, fragments: Optional[list] = None) -> list:
    """조각별 전사에서 반복 루프를 찾아낸 목록을 돌려준다. DB 를 만지지 않는다.

    반환: [{fragment_id, start, end, unit, repeat_count, coverage, text_len}]
    """
    from rough_cut.transcript_reader import detect_repetition_hallucination

    times = {}
    for f in (fragments or []):
        fid = f.get("fragment_id")
        if fid:
            times[fid] = (f.get("start_time"), f.get("end_time"))

    found = []
    for fid, text in (fragment_transcripts or {}).items():
        text = (text or "").strip()
        if not text:
            continue
        finding = detect_repetition_hallucination(text)
        if finding is None:
            continue
        start, end = times.get(fid, (None, None))
        found.append({
            "fragment_id": fid,
            "start": start,
            "end": end,
            "unit": finding.unit,
            "repeat_count": finding.repeat_count,
            "coverage": finding.coverage,
            "text_len": len(text),
        })
    found.sort(key=lambda r: (r["start"] is None, r["start"]))
    return found


def report(
    source_id: str,
    whisper_res: dict,
    fragments: Optional[list] = None,
    *,
    program_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[int]:
    """반복 루프를 원장에 신고한다. 신고할 것이 없으면 None.

    호출부는 이 함수의 예외를 잡아 **표시**하되 본선을 죽이지 않는다(2절).
    성공은 적지 않는다 — 원장이 가벼워야 오래 산다(failure_ledger 절벽 ③).
    """
    if not enabled():
        return None

    transcripts = whisper_res.get("fragment_transcripts") or {}
    found = scan(transcripts, fragments)
    if not found:
        return None

    import failure_ledger

    n_with_text = sum(1 for t in transcripts.values() if (t or "").strip())
    items = found[:_DETAIL_MAX_ITEMS]
    detail = {
        "total_flagged": len(found),
        "fragments_with_text": n_with_text,
        "fragments_total": len(transcripts),
        # 규모를 한 값으로 — "몇 %가 루프인가". 화면·다음 처방이 읽는 값이다.
        "flagged_ratio": round(len(found) / n_with_text, 4) if n_with_text else None,
        "asr_provider": whisper_res.get("provider"),
        "asr_fallback": whisper_res.get("asr_fallback"),
        "max_context_zero": os.getenv("CCUT_ASR_MAX_CONTEXT_ZERO", "1"),
        "program_id_resolution": whisper_res.get("program_id_resolution"),
        "program_id_candidates": whisper_res.get("program_id_candidates"),
        "detector": "rough_cut.transcript_reader.detect_repetition_hallucination",
        "truncated": len(found) > len(items),
        "items": items,
    }
    row_id = failure_ledger.record(
        DOMAIN,
        ERROR_CODE,
        program_id=program_id,
        source_id=source_id,
        phase="transcribe",
        detail=detail,
        db_path=db_path,
    )
    print(f"[ASR-REPORT] {source_id} 반복 루프 {len(found)}/{n_with_text} 조각 "
          f"({detail['flagged_ratio']}) — 원장 {DOMAIN}/{ERROR_CODE} #{row_id}",
          flush=True)
    return row_id


def report_safe(source_id: str, whisper_res: dict, fragments=None, **kw) -> Optional[int]:
    """본선 보호막. 신고가 실패해도 ASR 은 완주하되, 실패는 조용히 삼키지 않는다."""
    try:
        return report(source_id, whisper_res, fragments, **kw)
    except Exception as e:
        print(f"[ASR-REPORT][FAIL] {source_id} 신고 실패 — 본선은 계속 진행한다: {e}",
              flush=True)
        traceback.print_exc()
        return None
