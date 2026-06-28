import time

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "OK", "timestamp": time.time()}


@router.get("/pipeline/status")
async def pipeline_status():
    """[WATCHDOG] 파이프라인 전체 상태 진단 API"""
    try:
        from engine.pipeline_watchdog import run_watchdog
        result = run_watchdog(silent=True)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/system/diagnostics")
async def system_diagnostics():
    # [FIX-RUNTIME-1a] GPU ASR 런타임 환경진단(read 전용). /health(liveness)와 분리.
    from ai.diagnostics import collect_diagnostics
    return collect_diagnostics()
