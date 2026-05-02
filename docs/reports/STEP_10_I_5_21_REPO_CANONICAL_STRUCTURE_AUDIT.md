# STEP 10-I.5.21-R1 Repo Canonical Structure Audit

## 1. 개요
Codex 감사 시 발생할 수 있는 브랜치 혼선 및 구형 폴더 구조(`ui/`, `ccut_core/`) 참조 문제를 방지하기 위해, CCUT 1.0.4의 표준 저장소 구조를 정의하고 검증합니다.

## 2. 저장소 기준 정보
- **Repo URL:** https://github.com/rmina1000-bit/CCUT.git
- **Canonical Branch:** `ccut-1.0.4-step9`
- **Canonical Path:** 
  - Backend: `ccut_backend/`
  - Frontend: `ccut_frontend/`
- **Current HEAD:** (검수 시 `git rev-parse HEAD`로 확인)

## 3. 구조 검증 결과 (Pre-Audit Check)
- **`ccut_backend/main.py`**: 존재함
- **`ccut_frontend/src/pages/Index.tsx`**: 존재함
- **`docs/reports/`**: 존재함 (감사 요청서 및 증거 문서 포함)
- **구형 구조 (`ui/`, `ccut_core/`)**: 제거됨 (현재 브랜치 기준)

## 4. Codex 재검수 시 Preflight 명령
감사 시작 전, Codex는 반드시 아래 명령을 수행하여 환경을 초기화해야 합니다.

```bash
# 1. 독립된 작업 공간 생성 및 클론
rm -rf /workspace/CCUT_AUDIT_CORRECT
git clone https://github.com/rmina1000-bit/CCUT.git /workspace/CCUT_AUDIT_CORRECT
cd /workspace/CCUT_AUDIT_CORRECT

# 2. 기준 브랜치 전환 및 정합성 확인
git fetch origin
git checkout ccut-1.0.4-step9
git pull origin ccut-1.0.4-step9

# 3. 필수 파일 존재 여부 체크 (Preflight)
test -f ccut_backend/main.py || { echo "CRITICAL: ccut_backend/main.py missing"; exit 1; }
test -f ccut_frontend/src/pages/Index.tsx || { echo "CRITICAL: ccut_frontend/src/pages/Index.tsx missing"; exit 1; }
test -f docs/reports/CODEX_REQUEST_STEP_10_I_5_21_PIPELINE_AUDIT.md || { echo "CRITICAL: Audit Request missing"; exit 1; }

# 4. 현재 상태 확인
git rev-parse HEAD
git branch --show-current
```

## 5. Codex 검수 가이드
- **브랜치 고정**: 모든 감사는 `ccut-1.0.4-step9` 브랜치를 기준으로 수행합니다. `work` 또는 `main` 브랜치의 구형 구조를 참조해서는 안 됩니다.
- **경로 고정**: 프론트엔드는 `ccut_frontend/`, 백엔드는 `ccut_backend/` 경로를 사용합니다. `ui/` 폴더 기반의 분석은 무효입니다.
- **보고서 대상**: `docs/reports/CODEX_REQUEST_STEP_10_I_5_21_PIPELINE_AUDIT.md`에 명시된 질문에 대해서만 답변합니다.
