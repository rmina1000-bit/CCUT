"""[LAB-42] ASR CPU 자동 폴백 — GPU(Vulkan) 실패가 job FAILED로 끝나지 않게.

구조(2026-07-30 실측):
  - 로드 실패: main.py 가 adapter._ensure_loaded() 예외를 받아 job FAILED 처리.
  - 실행 실패: whisper_vulkan_adapter.transcribe_fragments 가 빈 transcript +
    provider_error 를 담아 반환 → 전 조각 asr_error.
  둘 다 "사용자에겐 그냥 실패"였다. whisper(CPU)는 설치·모델 캐시 모두 살아 있고
  evidence_board 215건 전부 whisper_vulkan — CPU 경로는 잠들어 있었을 뿐이다.

원칙:
  - 수동 우선권 유지: config.yaml active.asr 는 그대로 존중. 폴백은 그 위 안전망.
  - 조용한 강하 금지: 폴백 시 [ASR-FALLBACK] 사유를 반드시 로그에 남기고,
    결과 dict 의 provider/fallback 필드로 UI·DB(metadata_json)까지 전달한다.
  - 게이트: CCUT_ASR_CPU_FALLBACK (기본 1). 0 이면 구동작(실패는 실패) 그대로.
"""
import os
import time


def enabled() -> bool:
    return os.getenv("CCUT_ASR_CPU_FALLBACK", "1") in ("1", "true", "True")


def _cpu_adapter():
    """CPU(openai-whisper) 어댑터 인스턴스. config의 whisper 설정을 재사용."""
    from .registry import get_registry
    from .adapters.whisper_adapter import WhisperAdapter
    cfg = (get_registry().config.get("providers", {})
           .get("whisper", {}).get("config", {}) or {})
    return WhisperAdapter(cfg)


def transcribe_with_fallback(adapter, video_path: str, fragments: list,
                             load_error: str = None) -> dict:
    """활성 어댑터로 전사하되, 실패하면 CPU로 자동 강하해 결과를 채운다.

    load_error: 활성 어댑터 로드 자체가 실패한 경우 그 사유(전사 시도 없이 바로 폴백).
    반환 dict 는 기존 계약과 동일 + asr_fallback / asr_fallback_reason 추가.
    """
    reason = None
    result = None

    if load_error:
        reason = f"load_failed:{load_error}"
    else:
        try:
            result = adapter.transcribe_fragments(video_path, fragments)
            perr = result.get("provider_error")
            if perr:
                reason = f"provider_error:{perr}"
            elif not any((t or "").strip()
                         for t in result.get("fragment_transcripts", {}).values()):
                # 전 조각 공백 + rejected 가 asr_error 계열이면 전사 자체가 죽은 것.
                rej = set((result.get("rejected_fragments") or {}).values())
                if rej and rej <= {"asr_error"}:
                    reason = "all_fragments_asr_error"
        except Exception as e:
            reason = f"exception:{e}"

    if reason is None:
        return result

    if not enabled():
        print(f"[ASR-FALLBACK] gate off (CCUT_ASR_CPU_FALLBACK=0) — 폴백 안 함. "
              f"사유={reason}", flush=True)
        if result is not None:
            result["asr_fallback"] = None
            result["asr_fallback_reason"] = f"gate_off:{reason}"
            return result
        raise RuntimeError(f"ASR 로드 실패(폴백 게이트 off): {load_error}")

    print(f"[ASR-FALLBACK] GPU 경로 실패 → CPU(whisper)로 자동 강하. 사유={reason}",
          flush=True)
    t0 = time.time()
    try:
        cpu = _cpu_adapter()
        out = cpu.transcribe_fragments(video_path, fragments)
        elapsed = time.time() - t0
        if out.get("provider_error"):
            print(f"[ASR-FALLBACK][FAIL] CPU 경로도 실패: {out['provider_error']} "
                  f"({elapsed:.1f}s)", flush=True)
            out["asr_fallback"] = "cpu_failed"
        else:
            n_text = sum(1 for t in out.get("fragment_transcripts", {}).values()
                         if (t or "").strip())
            print(f"[ASR-FALLBACK][OK] adapter=cpu_fallback provider=whisper "
                  f"조각 {n_text}/{len(fragments)} 전사, {elapsed:.1f}s", flush=True)
            out["asr_fallback"] = "cpu_fallback"
        out["asr_fallback_reason"] = reason
        out["provider"] = "whisper_cpu_fallback"
        return out
    except Exception as e:
        print(f"[ASR-FALLBACK][FAIL] CPU 폴백 예외: {e}", flush=True)
        if result is not None:
            result["asr_fallback"] = "cpu_failed"
            result["asr_fallback_reason"] = f"{reason} | cpu_exception:{e}"
            return result
        raise
