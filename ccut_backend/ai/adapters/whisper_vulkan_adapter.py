"""Whisper.cpp Vulkan Adapter · GPU(Vulkan) 가속 ASR.

whisper-cli.exe(small, Vulkan) 를 호출해 영상 전체를 1회 전사한 뒤,
engine.ai_engine.transcribe_full_then_split 와 동일한 계약 dict 로 변환한다.

계약(transcribe_fragments 반환):
  fragment_transcripts : {frag_id: str}
  all_segments         : [{start:float(초), end:float(초), text:str, words:[word]}]
  fragment_words       : {frag_id: [word]}
  words                : [word]   word = {word:str, start:float, end:float, probability:float}
  language / provider / provider_error / rejected_fragments

검증 근거: Phase 1-GPU-BRIDGE — 계약 키/단위 일치(불일치 0), end-to-end x2(openai 대비),
          VRAM Vulkan0 ~670MB/8GB GPU 실사용 확인.
"""
import os
import re
import json
import time
import tempfile
import subprocess
from typing import Optional
from ..interface import ASRProvider
from ..schemas import TranscriptResult, HealthStatus
from .base import BaseAdapter

_SPECIAL = re.compile(r"^\s*[\[<]")  # [_BEG_], <|...|> 등 특수토큰


def _tokens_to_words(tokens: list) -> list:
    """whisper.cpp 토큰 → CCUT word 객체. 앞 공백 = 새 단어 경계, ms→초."""
    words = []
    cur = None
    for t in tokens:
        txt = t.get("text", "")
        if not txt or _SPECIAL.match(txt) or t.get("id", 0) >= 50256:
            continue
        off = t.get("offsets", {})
        s = off.get("from", 0) / 1000.0
        e = off.get("to", 0) / 1000.0
        p = float(t.get("p", 0.0))
        if txt.startswith(" ") or cur is None:
            if cur:
                cur["probability"] = round(sum(cur["_ps"]) / len(cur["_ps"]), 4)
                del cur["_ps"]
                words.append(cur)
            cur = {"word": txt, "start": round(s, 3), "end": round(e, 3), "_ps": [p]}
        else:
            cur["word"] += txt
            cur["end"] = round(e, 3)
            cur["_ps"].append(p)
    if cur:
        cur["probability"] = round(sum(cur["_ps"]) / len(cur["_ps"]), 4)
        del cur["_ps"]
        words.append(cur)
    return words


class WhisperVulkanAdapter(BaseAdapter, ASRProvider):
    model_id = "whisper-cpp-vulkan-small"
    adapter_version = "1.0"

    def __init__(self, config: dict):
        super().__init__(config)
        cfg = config or {}
        # [FIX-RUNTIME-0] 표준 런타임 위치(프로젝트 루트/runtime/whisper-vulkan). 외부경로(D:/CCUT_EXTERNAL_DATA) 의존 제거.
        # _ROOT = 이 파일(ccut_backend/ai/adapters/)에서 3단계 상위 = 프로젝트 루트(D:/CCUT1.0.4).
        _ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        _RT = os.path.join(_ROOT, "runtime", "whisper-vulkan")

        def _resolve(p: str) -> str:
            # 절대경로는 그대로, 상대경로는 프로젝트 루트 기준으로 해석(서버 실행 cwd 무관 보장).
            return p if os.path.isabs(p) else os.path.join(_ROOT, p)

        self.cli_path = _resolve(cfg.get("cli_path", os.path.join(_RT, "whisper-cli.exe")))
        self.model_path = _resolve(cfg.get("model_path", os.path.join(_RT, "models", "ggml-small.bin")))
        self.fallback_model_path = _resolve(cfg.get("fallback_model_path", os.path.join(_RT, "models", "ggml-base.bin")))
        self.threads = int(cfg.get("threads", 6))
        self._active_model = None

    def _ensure_loaded(self):
        if self._loaded:
            return
        # [GUARD] 외부경로 의존 — 없으면 silent fail 금지, 명확·actionable 에러 발생.
        #   복구: config.yaml providers.whisper_vulkan.config.cli_path 수정,
        #         또는 active.asr 를 whisper(openai, CPU)로 되돌려 폴백.
        if not os.path.exists(self.cli_path):
            self._load_error = (
                f"whisper_vulkan 비활성: whisper-cli 없음 ({self.cli_path}). "
                f"config.yaml providers.whisper_vulkan.config.cli_path 확인 또는 active.asr=whisper 로 폴백."
            )
            self._loaded = False
            print(f"[WhisperVulkan][FATAL] {self._load_error}", flush=True)
            raise RuntimeError(self._load_error)
        # 모델 선택 (small 1순위, 없으면 base fallback)
        if os.path.exists(self.model_path):
            self._active_model = self.model_path
        elif os.path.exists(self.fallback_model_path):
            self._active_model = self.fallback_model_path
            print(f"[WhisperVulkan] small 모델 없음 → base fallback: {self.fallback_model_path}", flush=True)
        else:
            self._load_error = (
                f"whisper_vulkan 비활성: 모델 없음 ({self.model_path} / {self.fallback_model_path}). "
                f"config.yaml model_path 확인 또는 active.asr=whisper 로 폴백."
            )
            self._loaded = False
            print(f"[WhisperVulkan][FATAL] {self._load_error}", flush=True)
            raise RuntimeError(self._load_error)
        self._loaded = True
        self._load_error = None
        # 실제 사용 모델 크기 (metadata 라벨용 — main.py가 active provider에서 읽음)
        self.active_model_size = "small" if self._active_model == self.model_path else "base"

    # ──────────────────────────────────────────────
    def _extract_wav(self, video_path: str) -> str:
        cli_dir = os.path.dirname(self.cli_path)
        fd, wav = tempfile.mkstemp(suffix=".wav", dir=cli_dir)
        os.close(fd)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
             "-vn", "-ac", "1", "-ar", "16000", wav],
            check=True, timeout=180,
        )
        return wav

    def _run_cli(self, wav: str):
        cli_dir = os.path.dirname(self.cli_path)
        of = os.path.join(cli_dir, f"_live_asr_{os.getpid()}")
        args = [self.cli_path, "-m", self._active_model, "-f", wav,
                "-t", str(self.threads), "-l", "auto", "-ojf", "-of", of]
        proc = subprocess.run(args, cwd=cli_dir, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=900)
        jpath = of + ".json"
        try:
            with open(jpath, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        finally:
            try:
                os.unlink(jpath)
            except Exception:
                pass
        log = (proc.stderr or "") + (proc.stdout or "")
        vram = re.findall(r"(Vulkan0 total size[^\n]*|using Vulkan0 backend|compute buffer[^\n]*MB)", log)
        return data, vram

    # ──────────────────────────────────────────────
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptResult:
        self._ensure_loaded()
        data, _ = self._run_cli(audio_path)
        segs = []
        full = []
        for seg in data.get("transcription", []):
            off = seg.get("offsets", {})
            txt = seg.get("text", "").strip()
            segs.append({"start": off.get("from", 0) / 1000.0,
                         "end": off.get("to", 0) / 1000.0, "text": txt})
            full.append(txt)
        result = TranscriptResult(
            segments=segs,
            full_text=" ".join(full).strip(),
            language_detected=data.get("result", {}).get("language", language or "unknown"),
            raw=data,
        )
        return self._stamp(result)

    def transcribe_fragments(self, video_path: str, fragments: list) -> dict:
        """영상 전체 1회 전사 후 fragment 시간범위로 분배 (whisper 경로와 동일 계약)."""
        try:
            self._ensure_loaded()
            wav = self._extract_wav(video_path)
            try:
                data, vram = self._run_cli(wav)
            finally:
                try:
                    os.unlink(wav)
                except Exception:
                    pass
            provider_error = None
        except Exception as e:
            print(f"[WhisperVulkan] 전사 실패: {e}")
            return {
                "fragment_transcripts": {f["fragment_id"]: "" for f in fragments},
                "all_segments": [],
                "fragment_words": {f["fragment_id"]: [] for f in fragments},
                "words": [],
                "language": "unknown",
                "provider": "whisper_vulkan",
                "provider_error": str(e),
                "rejected_fragments": {f["fragment_id"]: "asr_error" for f in fragments},
            }

        # 전체 segments / words (초 단위)
        all_segments = []
        all_words = []
        for seg in data.get("transcription", []):
            off = seg.get("offsets", {})
            sw = _tokens_to_words(seg.get("tokens", []))
            all_words.extend(sw)
            all_segments.append({
                "start": round(off.get("from", 0) / 1000.0, 3),
                "end": round(off.get("to", 0) / 1000.0, 3),
                "text": seg.get("text", "").strip(),
                "words": sw,
            })

        # fragment 분배 (transcribe_full_then_split 와 동일 로직)
        fragment_transcripts = {}
        fragment_words = {}
        rejected = {}
        for frag in fragments:
            fid = frag["fragment_id"]
            fs = float(frag.get("start_time", 0))
            fe = float(frag.get("end_time", 0))
            parts, fw = [], []
            for seg in all_segments:
                if seg["end"] <= fs or seg["start"] >= fe:
                    continue
                parts.append(seg["text"])
                fw.extend(seg.get("words", []))
            txt = " ".join(parts).strip()
            fragment_transcripts[fid] = txt
            fragment_words[fid] = fw
            if not txt:
                rejected[fid] = "empty_text"

        return {
            "fragment_transcripts": fragment_transcripts,
            "all_segments": all_segments,
            "fragment_words": fragment_words,
            "words": all_words,
            "language": data.get("result", {}).get("language", "unknown"),
            "provider": "whisper_vulkan",
            "provider_error": provider_error,
            "rejected_fragments": rejected,
        }

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=self._loaded and self._load_error is None,
            model_id=self.model_id,
            version=self.adapter_version,
            loaded=self._loaded,
            error=self._load_error,
        )
