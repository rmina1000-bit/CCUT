from observability.trace_chain import verify_trace_chain
from pathlib import Path

obs = Path("storage/observability")
for f in sorted(obs.glob("*.log")):
    print(f.name, verify_trace_chain(f))
