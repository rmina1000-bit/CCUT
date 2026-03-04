import shutil
from pathlib import Path
from observability.perf_guard import (
    measure_append,
    measure_replay,
    measure_verify,
    measure_render_cycle,
)
from observability.runtime_switch import enable, disable
from decision_log import DecisionLog
from render.render_planner import build_render_request
from render.queue import enqueue_render
from render.worker import process_queue_once


def _reset():
    if Path("storage").exists():
        shutil.rmtree("storage")


def render_cycle():
    req = build_render_request()
    enqueue_render(req)
    process_queue_once()


def _run_measurements():
    log = DecisionLog()
    append_ms = measure_append(log, 200)
    replay_ms = measure_replay(log)
    verify_ms = measure_verify(log)
    render_ms = measure_render_cycle(render_cycle)
    return append_ms, replay_ms, verify_ms, render_ms


print("=== Observability ON ===")
_reset()
enable()
a_on, r_on, v_on, rnd_on = _run_measurements()
print(f"  Append avg(ms) : {a_on}")
print(f"  Replay     (ms): {r_on}")
print(f"  Verify     (ms): {v_on}")
print(f"  Render cycle(ms): {rnd_on}")

print("\n=== Observability OFF ===")
_reset()
disable()
a_off, r_off, v_off, rnd_off = _run_measurements()
print(f"  Append avg(ms) : {a_off}")
print(f"  Replay     (ms): {r_off}")
print(f"  Verify     (ms): {v_off}")
print(f"  Render cycle(ms): {rnd_off}")

enable()


def _overhead(on, off):
    if off == 0:
        return "N/A"
    return f"{((on - off) / off * 100):+.1f}%"


print("\n=== Overhead ===")
print(f"  Append : {_overhead(a_on, a_off)}")
print(f"  Replay : {_overhead(r_on, r_off)}")
print(f"  Verify : {_overhead(v_on, v_off)}")
print(f"  Render : {_overhead(rnd_on, rnd_off)}")
