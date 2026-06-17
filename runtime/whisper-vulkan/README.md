# runtime/whisper-vulkan — GPU ASR 표준 런타임 위치

CCUT GPU ASR(whisper.cpp Vulkan, `WhisperVulkanAdapter`)가 사용하는 외부 바이너리·모델의 **표준 위치**입니다.
기존에는 `D:/CCUT_EXTERNAL_DATA/whisper_vulkan_test`(머신 종속 절대경로)에 의존했으나,
FIX-RUNTIME-0에서 프로젝트 내부 표준 경로로 통일했습니다.

## 경로 해석
- `ccut_backend/ai/config.yaml` → `providers.whisper_vulkan.config` 의 `cli_path` / `model_path` / `fallback_model_path`
  는 프로젝트 루트 기준 **상대경로**(`runtime/whisper-vulkan/...`)로 기록됩니다.
- `WhisperVulkanAdapter` 가 `__file__` 기준으로 프로젝트 루트를 계산해 상대경로를 절대경로로 해석하므로,
  **서버 실행 cwd(루트/ccut_backend 무관)에 영향받지 않습니다.**

## 필요 파일 (8개)
실행에 필요한 자산. 모두 **git 비추적**(배포 자산 / 용량) — 이 디렉터리의 `.gitignore`가 바이너리·모델을 제외합니다.

| 파일 | 용도 |
|------|------|
| `whisper-cli.exe` | whisper.cpp CLI 실행기 |
| `ggml-vulkan.dll` | Vulkan 백엔드 |
| `ggml-base.dll` | ggml 백엔드 |
| `ggml-cpu.dll` | CPU 백엔드 |
| `ggml.dll` | ggml 코어 |
| `whisper.dll` | whisper 코어 |
| `models/ggml-small.bin` | 1순위 모델(small) |
| `models/ggml-base.bin` | 폴백 모델(base) |

## 출처
whisper.cpp (Windows, Vulkan 빌드). 원본 보관: `D:/CCUT_EXTERNAL_DATA/whisper_vulkan_test`.

## git 추적 정책
이 폴더에서 git이 추적하는 것은 `.gitignore` 와 `README.md` 뿐입니다.
바이너리·모델(`*.exe`, `*.dll`, `models/*.bin`)은 추적하지 않습니다.
새 환경 구성 시 위 8개 파일을 이 위치에 배치하면 됩니다.
