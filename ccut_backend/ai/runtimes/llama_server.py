"""llama-server 프로세스 관리 헬퍼.

각 모델별로 llama-server 프로세스를 기동·종료·헬스체크한다.
OpenAI 호환 API(/v1/chat/completions)를 통해 Adapter에서 호출.
"""

import os
import time
import subprocess
import atexit
from typing import Optional, List
import urllib.request
import urllib.error
import json


class LlamaServerRunner:
    """llama-server 하나를 담당하는 런너."""

    def __init__(
        self,
        server_binary: str,
        model_path: str,
        mmproj_path: Optional[str] = None,
        port: int = 8090,
        ctx_size: int = 4096,
        n_gpu_layers: int = 0,
        extra_args: Optional[List[str]] = None,
    ):
        self.server_binary = server_binary
        self.model_path = model_path
        self.mmproj_path = mmproj_path
        self.port = port
        self.ctx_size = ctx_size
        self.n_gpu_layers = n_gpu_layers
        self.extra_args = extra_args or []
        self._process: Optional[subprocess.Popen] = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _build_cmd(self) -> list:
        cmd = [
            self.server_binary,
            "-m", self.model_path,
            "--port", str(self.port),
            "--host", "127.0.0.1",
            "--ctx-size", str(self.ctx_size),
            "--n-gpu-layers", str(self.n_gpu_layers),
        ]
        if self.mmproj_path:
            cmd += ["--mmproj", self.mmproj_path]
        cmd += self.extra_args
        return cmd

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def is_healthy(self, timeout: float = 2.0) -> bool:
        """llama-server /health 엔드포인트 체크."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def start(self, wait_ready_sec: int = 60) -> bool:
        if self.is_running():
            return True
        if not os.path.exists(self.server_binary):
            print(f"[LlamaServer] 실행파일 없음: {self.server_binary}")
            return False
        if not os.path.exists(self.model_path):
            print(f"[LlamaServer] 모델파일 없음: {self.model_path}")
            return False

        cmd = self._build_cmd()
        print(f"[LlamaServer] 기동: {' '.join(cmd)}")
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as e:
            print(f"[LlamaServer] 기동 실패: {e}")
            return False

        atexit.register(self.stop)

        deadline = time.time() + wait_ready_sec
        while time.time() < deadline:
            if self.is_healthy():
                print(f"[LlamaServer] 준비 완료 · port={self.port}")
                return True
            if not self.is_running():
                print(f"[LlamaServer] 프로세스 비정상 종료")
                return False
            time.sleep(1)

        print(f"[LlamaServer] 타임아웃 ({wait_ready_sec}s)")
        return False

    def stop(self):
        if self._process is None:
            return
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        except Exception:
            pass
        self._process = None

    def post_json(self, path: str, payload: dict, timeout: int = 120) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
