from decision_log import DecisionLog
from verify_engine import verify_engine
from observability.trace_verifier import verify_trace_determinism


def scenario():
    log = DecisionLog()
    log.append("CREATE_CUT", {"id": "c1", "start": 0, "end": 5})
    verify_engine(log)


print("Deterministic:", verify_trace_determinism(scenario))
