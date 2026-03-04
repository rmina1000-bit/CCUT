from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class EngineView:
    status: str
    last_seq: int
    meta: Dict[str, Any]
