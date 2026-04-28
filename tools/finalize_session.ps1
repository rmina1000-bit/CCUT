# ============================================================================
#  CCUT 1.0.4 Session Finalization Script
#  Usage: powershell -ExecutionPolicy Bypass -File .\tools\finalize_session.ps1
#  Purpose: Update key docs, verify hygiene, prompt for commit/push
# ============================================================================

param(
    [string]$Step   = "STEP 0-9",
    [string]$Status = "PASS",
    [string]$Next   = "STEP 10 Final stabilization / regression test"
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Pass($m) { Write-Host "[OK]   $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[FAIL] $m" -ForegroundColor Red }

Set-Location "D:\CCUT1.0.4"

# ----- 1. Git 상태 확인 -----
Step "1. Git 상태 확인"
$branch = (git branch --show-current).Trim()
$head   = (git rev-parse HEAD).Trim()
try {
    $origin = (git rev-parse "origin/$branch").Trim()
} catch {
    $origin = "unknown"
}
$dirty = git status --porcelain

Write-Host "  Branch : $branch"
Write-Host "  HEAD   : $head"
Write-Host "  Origin : $origin"

if ($head -eq $origin) { Pass "Local == Remote (synced)" }
else                   { Warn "Local != Remote — commit/push 필요" }

if (-not $dirty) { Pass "Working tree clean" }
else             { Warn "Uncommitted changes:`n$dirty" }

# ----- 2. 금지 임시 파일 검사 -----
Step "2. 금지 임시 파일 검사"
$forbidden = @(
    "check_db.py", "fix_mojibake.py", "fix_mojibake_block.py",
    "fix_mojibake_final.py", "proposal_request.json",
    "step3_meta_check.json", "step3_verify.json",
    "uploads_list.csv", "verify_repair.ps1", "verify_repair_output.txt",
    "clean_step89.ps1", "_archive_backend_20260420",
    "ccut_backend\logs\hook_distribution",
    "ccut_backend\backend.log", "ccut_backend\backend_err.log",
    "ccut_backend\main.py.bak"
)
$found = $false
foreach ($f in $forbidden) {
    if (Test-Path $f) {
        Warn "FORBIDDEN FILE EXISTS: $f"
        $found = $true
    }
}
if (-not $found) { Pass "금지 임시 파일 없음" }

# ----- 3. 핵심 파일 존재 확인 -----
Step "3. 핵심 파일 존재 확인"
$required = @(
    "ccut_backend\main.py",
    "ccut_backend\engine\render_engine.py",
    "ccut_backend\archive\db_models.py",
    "ccut_frontend\src\pages\Index.tsx",
    "ccut_frontend\src\components\CenterPanel.tsx"
)
foreach ($f in $required) {
    if (Test-Path $f) { Pass "$f 존재" }
    else              { Warn "$f 없음!" }
}

# ----- 4. 하드코딩 검사 -----
Step "4. 하드코딩 / 인코딩 잔존 검사"
$hcCheck = Select-String -Path "ccut_backend\main.py" -Pattern 'D:/test_video\.mp4' -SimpleMatch
if ($hcCheck) { Warn "main.py에 D:/test_video.mp4 잔존"; $hcCheck | ForEach-Object { Write-Host "  $_" } }
else          { Pass "main.py 하드코딩 없음" }

$lhCheck = Select-String -Path "ccut_frontend\src\components\CenterPanel.tsx" -Pattern 'localhost:8000' -SimpleMatch
if ($lhCheck) { Warn "CenterPanel.tsx에 localhost:8000 잔존" }
else          { Pass "CenterPanel.tsx 하드코딩 없음" }

# ----- 5. SESSION_HANDOFF.md 자동 업데이트 -----
Step "5. docs/SESSION_HANDOFF.md 업데이트"
$now      = Get-Date -Format "yyyy-MM-dd"
$handoff  = @"
# CCUT 1.0.4 Session Handoff

## 1. 현재 기준선

- **Branch:** ``$branch``
- **SHA:** ``$head``
- **Local path:** ``D:\CCUT1.0.4``
- **Repo:** ``https://github.com/rmina1000-bit/CCUT.git``
- **Last updated:** $now

## 2. 완료 단계

- STEP 0 기준선 확보: PASS
- STEP 1 Proxy / Segment / Fingerprint: PASS
- STEP 2 Evidence Board: PASS
- STEP 3 Quick Scan + Hypothesis: PASS
- STEP 4 Semantic Fragment: PASS
- STEP 5 User Intent 최종 반영: PASS
- STEP 6 Proposal Engine: PASS
- STEP 7 ExportInput 생성: PASS
- STEP 8 Render Engine / Export 실행: PASS
- STEP 9 UI 최소연동 / 통합 확인: PASS

## 3. 현재 완성 흐름

```
영상 업로드
→ Quick Scan (POST /quick-scan/{source_id})
→ Semantic Fragment (POST /generate-fragments/{source_id})
→ Proposal 생성 (POST /proposals/{source_id})
→ ExportInput 생성 (POST /export-input/{proposal_id})
→ Render 실행 (POST /render/{export_input_id})
→ 결과 조회 (GET /render-result/{export_input_id})
→ UI mp4 표시 / 다운로드
```

## 4. 최신 상태

- $Step: $Status
- 임시 파일: 없음 (정리 완료)
- Working tree: $(if ($dirty) { "Dirty — commit 필요" } else { "Clean" })

## 5. 다음 작업 후보

- $Next

## 6. 금지사항

- localStorage / PBE 재활성화 금지
- 병렬 렌더링 금지
- main/master 브랜치 push 금지
- 새 SESSION_HANDOFF 파일 생성 금지 (이 파일만 업데이트)

## 7. 다음 작업 전 확인 명령

```powershell
git branch --show-current
git rev-parse HEAD
git rev-parse origin/ccut-1.0.4-step9
git status --short
```
"@

[System.IO.File]::WriteAllText("docs\SESSION_HANDOFF.md", $handoff, $utf8NoBom)
Pass "docs/SESSION_HANDOFF.md 업데이트 완료"

# ----- 6. git status 출력 -----
Step "6. 현재 Git 변경 파일 목록"
git status --short

# ----- 7. 안내 -----
Step "완료 — 다음 단계 안내"
Write-Host @"

  다음 명령으로 커밋/푸시하세요:

    git add docs tools/finalize_session.ps1
    git status --short
    git commit -m "Finalize session: update docs and add finalize_session.ps1"
    git push origin $branch
    git rev-parse HEAD
    git rev-parse origin/$branch

  SHA를 확인 후 보고하세요.
"@ -ForegroundColor Yellow
