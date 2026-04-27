"""Qwen3-ASR Adapter · llama-server를 통한 음성 전사.

llama-server가 기동되어 있어야 하며, /v1/chat/completions 에
audio 데이터를 base64로 담아 전사를 받는다.
"""

import os
import base64
from typing import Optional
from ..interface import ASRProvider
from ..schemas import TranscriptResult, HealthStatus
from ..runtimes import LlamaServerRunner
from .base import BaseAdapter


class Qwen3ASRAdapter(BaseAdapter, ASRProvider):
    model_id = "qwen3-asr-0.6b"
    adapter_version = "1.0"

    def __init__(self, config: dict):
        super().__init__(config)
        self._runner: Optional[LlamaServerRunner] = None

    def _ensure_loaded(self):
        # [B2-03] runner 객체는 Adapter 수명 동안 1회만 생성
        if self._runner is None:
            try:
                self._runner = LlamaServerRunner(
                    server_binary=self.config["server_binary"],
                    model_path=self.config["model_path"],
                    mmproj_path=self.config.get("mmproj_path"),
                    port=int(self.config.get("port", 8091)),
                    ctx_size=int(self.config.get("ctx_size", 4096)),
                    n_gpu_layers=int(self.config.get("n_gpu_layers", 0)),
                )
            except Exception as e:
                self._loaded = False
                self._load_error = f"LlamaServerRunner 생성 실패: {e}"
                raise

        # 이미 healthy 면 종료
        if self._runner.is_healthy():
            self._loaded = True
            self._load_error = None
            return

        # healthy 아니면 start() 재시도
        # (start() 내부에 is_running() 체크 있음 → 프로세스 살아있으면 skip)
        if not self._runner.start():
            self._loaded = False
            self._load_error = "llama-server 기동 실패"
            raise RuntimeError(self._load_error)

        self._loaded = True
        self._load_error = None

    @staticmethod
    def _audio_base64(path: str) -> str:
        """파일을 순수 base64 문자열로 인코딩.

        llama.cpp 의 input_audio.data 는 data URL 접두사 없는
        순수 base64 만 받는다.
        """
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    @staticmethod
    def _has_audio_stream(video_path: str) -> bool:
        """ffprobe로 오디오 스트림 존재 여부 확인.

        체크 자체가 실패하면 False 가 아닌 True 를 반환하여
        기존 경로(ffmpeg 시도)를 그대로 진행시킨다 (안전 fallback).
        """
        import subprocess
        try:
            result = subprocess.run([
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path,
            ], capture_output=True, text=True, timeout=10)
            return bool(result.stdout.strip())
        except Exception:
            # ffprobe 자체 실패 시 기존 경로 진행
            return True

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> TranscriptResult:
        self._ensure_loaded()
        audio_b64 = self._audio_base64(audio_path)

        # format 필드는 실제 파일 확장자 기반 (wav / mp3 지원)
        ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
        audio_format = ext if ext in ("wav", "mp3") else "wav"

        prompt = "Transcribe the audio."
        if language:
            prompt += f" Language: {language}."

        payload = {
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "temperature": 0.0,
            "max_tokens": 2048,
        }
        raw = self._runner.post_json("/v1/chat/completions", payload, timeout=300)
        _dbg_content = raw.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')
        print(f"[Qwen3ASR DEBUG] raw_content={_dbg_content!r}", flush=True)

        text = ""
        try:
            text = raw["choices"][0]["message"]["content"]
        except Exception:
            text = ""

        # [FILTER] Qwen3-ASR 자동 태그 제거
        # 원본: "language Korean<asr_text>실제 전사 내용</asr_text>"
        # 결과: "실제 전사 내용"
        if "<asr_text>" in text:
            text = text.split("<asr_text>", 1)[1]
        text = text.replace("</asr_text>", "")

        # 특수 토큰 제거 (모델이 간혹 반환하는 것들)
        for _tok in ("<|audio_bos|>", "<|audio_eos|>", "<|endoftext|>"):
            text = text.replace(_tok, "")

        text = text.strip()

        print(f"[Qwen3ASR DEBUG] text_after_filter={text!r}", flush=True)

        result = TranscriptResult(
            segments=[],
            full_text=text.strip(),
            language_detected=language or "unknown",
            raw=raw,
        )
        return self._stamp(result)

    def transcribe_fragments(self, video_path: str, fragments: list) -> dict:
        """fragment별 오디오를 추출하여 전사.

        주의: 현재는 단순 구현 (fragment마다 ffmpeg로 슬라이스 → 전사).
        실제 B2에서 성능 개선 여지 있음.
        """
        import tempfile
        import subprocess

        results = {}
        # [B2-01] 오디오 스트림 선체크 — 없으면 전체 skip
        if not self._has_audio_stream(video_path):
            print(f"[Qwen3ASR] 오디오 스트림 없음, 전사 skip: {video_path}")
            for frag in fragments:
                results[frag["fragment_id"]] = ""
            return results

        for frag in fragments:
            frag_id = frag["fragment_id"]
            start = float(frag.get("start_time", 0))
            end = float(frag.get("end_time", start))
            duration = max(0.1, end - start)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                subprocess.run([
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", str(start),
                    "-i", video_path,
                    "-t", str(duration),
                    "-vn", "-ac", "1", "-ar", "16000",
                    tmp_path,
                ], check=True, timeout=60)
                tr = self.transcribe(tmp_path)
                results[frag_id] = tr.full_text
            except Exception as e:
                print(f"[Qwen3ASR] frag {frag_id} 전사 실패: {e}")
                results[frag_id] = ""
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return results

    def health_check(self) -> HealthStatus:
        if self._runner and self._runner.is_healthy():
            return HealthStatus(
                ok=True, model_id=self.model_id,
                version=self.adapter_version, loaded=True,
            )
        return HealthStatus(
            ok=False, model_id=self.model_id,
            version=self.adapter_version, loaded=self._loaded,
            error=self._load_error,
        )
