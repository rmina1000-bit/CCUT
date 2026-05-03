"""Provider descriptor skeleton for the CCUT AI Boundary.

This module is intentionally not imported by runtime code.
It defines provider classification types for future AI boundary work.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class ProviderCategory(Enum):
    """Classification categories for AI-related components."""

    CORE = auto()
    ACTIVE_PROVIDER = auto()
    PASS_THROUGH_PROVIDER = auto()
    FUTURE_PROVIDER = auto()
    FALLBACK_PROVIDER = auto()
    RULE_BASED_FALLBACK = auto()
    PLACEHOLDER = auto()


@dataclass(frozen=True)
class ProviderDescriptor:
    """Static descriptor for an AI provider or AI-adjacent component."""

    name: str
    category: ProviderCategory
    module_path: Optional[str] = None
    notes: Optional[str] = None
