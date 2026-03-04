from dataclasses import dataclass, field
import uuid

@dataclass(frozen=True)
class Cut:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start: float = 0.0
    end: float = 0.0

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError("Cut start must be less than end")
