import time


def measure_append(log, n: int = 100) -> float:
    """n회 append 평균 소요 시간 (ms)"""
    times = []
    for i in range(n):
        start = time.perf_counter()
        log.append("CREATE_CUT", {
            "id": f"perf_{i}",
            "start": float(i),
            "end": float(i + 1)
        })
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    return round(sum(times) / len(times), 3)


def measure_replay(log) -> float:
    """기존 storage에서 DecisionLog 복원 소요 시간 (ms)"""
    from decision_log import DecisionLog

    storage_path = log._persistence._log_path
    start = time.perf_counter()
    DecisionLog(storage_path)
    elapsed = (time.perf_counter() - start) * 1000
    return round(elapsed, 3)


def measure_verify(log) -> float:
    """verify_engine 9단 체인 소요 시간 (ms)"""
    from verify_engine import verify_engine

    start = time.perf_counter()
    verify_engine(log)
    elapsed = (time.perf_counter() - start) * 1000
    return round(elapsed, 3)


def measure_render_cycle(run_fn) -> float:
    """enqueue → process_once 전체 사이클 소요 시간 (ms)"""
    start = time.perf_counter()
    run_fn()
    elapsed = (time.perf_counter() - start) * 1000
    return round(elapsed, 3)
