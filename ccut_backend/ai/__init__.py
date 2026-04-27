"""CCUT AI Adapter System.

3계층 구조:
  Layer 1 · Interface (계약)
  Layer 2 · Adapter (모델별 구현)
  Layer 3 · Runtime (실제 모델)

CCUT 본체는 이 모듈의 get_registry()만 사용한다.
"""

from .registry import get_registry, AIRegistry

__all__ = ["get_registry", "AIRegistry"]
