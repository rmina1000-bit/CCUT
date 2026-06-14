"""[FRAGMENT-SEARCH] 다국어 임베딩 모델 싱글톤.

paraphrase-multilingual-MiniLM-L12-v2 (384-dim).
- 서버 생애 1회만 로딩 (lazy)
- 한국어 쿼리 <-> 영어/한국어 묘사 cross-lingual 매칭
- 오프라인 강제 (HF_HUB_OFFLINE): 다운로드 시도 없이 캐시만 사용
"""
import os
import threading
import numpy as np

_MODEL = None
_LOCK = threading.Lock()
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_DIM = 384


def get_model():
    """임베딩 모델 싱글톤 반환 (lazy, thread-safe)."""
    global _MODEL
    if _MODEL is None:
        with _LOCK:
            if _MODEL is None:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import SentenceTransformer
                _MODEL = SentenceTransformer(_MODEL_NAME)
                print(f"[EMBED] 모델 로딩 완료: {_MODEL_NAME} ({_DIM}d)")
    return _MODEL


def encode_one(text: str) -> np.ndarray:
    """단일 텍스트 -> float32 정규화 벡터."""
    if not text or not text.strip():
        return np.zeros(_DIM, dtype=np.float32)
    vec = get_model().encode([text], normalize_embeddings=True)[0]
    return vec.astype(np.float32)


def encode_batch(texts: list) -> np.ndarray:
    """텍스트 배치 -> (N, 384) float32 정규화 행렬."""
    if not texts:
        return np.zeros((0, _DIM), dtype=np.float32)
    safe = [t if (t and t.strip()) else " " for t in texts]
    vecs = get_model().encode(safe, normalize_embeddings=True, batch_size=32)
    return vecs.astype(np.float32)


def to_bytes(vec: np.ndarray) -> bytes:
    """벡터 -> DB 저장용 bytes (float32)."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_bytes(b: bytes) -> np.ndarray:
    """DB bytes -> 벡터."""
    if not b:
        return np.zeros(_DIM, dtype=np.float32)
    return np.frombuffer(b, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """정규화 벡터 가정 시 내적 = cosine. 안전하게 정규화 포함."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


MODEL_NAME = _MODEL_NAME
DIM = _DIM
