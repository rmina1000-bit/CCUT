# CCUT 백엔드 감시 런처 (자동 재시작 + 크래시 로깅)
# - 백엔드가 죽으면 즉시 되살림 (연속 빠른 크래시는 백오프)
# - stdout/stderr를 ccut_backend/logs/ 에 타임스탬프로 보존 → 죽는 진짜 원인 포착
# - 이미 8000 떠 있으면 중복 기동 안 함
# 수동 실행: 우클릭 > PowerShell로 실행  /  또는  powershell -ExecutionPolicy Bypass -File run_backend_supervised.ps1
# 자동 실행: install_backend_autostart.ps1 로 로그인 시 자동 기동 등록

$ErrorActionPreference = "Continue"
$Root       = "D:\CCUT1.0.4"
$BackendDir = Join-Path $Root "ccut_backend"
$Python     = "C:\Users\rmina\AppData\Local\Programs\Python\Python312\python.exe"
$LogDir     = Join-Path $BackendDir "logs"
$SupLog     = Join-Path $LogDir "supervisor.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
if (-not (Test-Path $Python))  { $Python = "python" }   # 폴백: PATH의 python

$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = "T"

# [GATE-LOOP-01 0-2 2026-07-25] 게이트 강제 구문 제거 — 유일한 출처는 ccut_backend/.env.
# 구판은 여기서 5개(HUB_PLAN/AUTO_REINDEX/SINGLE_CACHE/LEGACY_NARRATIVE/PERSON_RELINK)를
# 세웠고 run_backend.ps1은 4개, run_backend.bat은 0개였다 — 같은 코드가 기동 경로에 따라
# 다른 제품으로 떴다. 그 값들은 .env로 이관됐다. 여기서 다시 세우면 .env를 이기므로
# (main.py load_dotenv override=False) 갈림이 부활한다. 세우지 않는다.

function Write-Sup($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $SupLog -Value $line -Encoding utf8
}

# 14일 지난 로그 정리
Get-ChildItem $LogDir -Filter "backend_*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 이미 떠 있으면 중복 기동 방지
# [GATE-LOOP-01 0-2] 포트 수정 8000 → 8011. main.py는 8011로 뜨는데(uvicorn.run port=8011)
# 가드가 8000을 보고 있어 '이미 떠 있음'을 영영 감지하지 못했다 → 같은 DB에 백엔드 2개가
# 붙는 경로였다(RUNTIME 격리 규칙 위반, 8011 사건과 같은 종류).
$BackendPort = 8011
$existing = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Sup "$BackendPort already listening (pid=$($existing.OwningProcess)). supervisor exit."
    exit 0
}

Write-Sup "=== supervisor start ==="
# [GATE-LOOP-01 0-2] 게이트는 이 스크립트가 세우지 않는다 — ccut_backend/.env가 유일한 출처.
# 실제로 무엇이 실렸는지는 백엔드 자신이 찍는다 (main.py 의 [ENV] 줄 + GET /settings/gates).
Write-Sup "gates: (ccut_backend/.env 단일 출처 — 런처는 세우지 않음)"
$fails = 0
while ($true) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $out = Join-Path $LogDir "backend_$stamp.out.log"
    $err = Join-Path $LogDir "backend_$stamp.err.log"
    Write-Sup "starting backend  (out=$([System.IO.Path]::GetFileName($out)))"
    $start = Get-Date

    $p = Start-Process -FilePath $Python -ArgumentList "main.py" -WorkingDirectory $BackendDir `
         -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -NoNewWindow
    $p.WaitForExit()
    $code = $p.ExitCode
    $dur  = [int](New-TimeSpan -Start $start -End (Get-Date)).TotalSeconds
    Write-Sup "backend EXITED code=$code after ${dur}s"

    # 크래시 원인 즉시 가시화: err 로그 마지막 20줄을 supervisor.log에 박음
    if (Test-Path $err) {
        $tail = Get-Content $err -Tail 20 -ErrorAction SilentlyContinue
        if ($tail) {
            Write-Sup "---- last stderr ($([System.IO.Path]::GetFileName($err))) ----"
            foreach ($l in $tail) { Add-Content -Path $SupLog -Value "    $l" -Encoding utf8 }
            Write-Sup "---- end stderr ----"
        }
    }

    # 연속 빠른 크래시(10초 미만)면 백오프 — tight crash loop 방지
    if ($dur -lt 10) { $fails++ } else { $fails = 0 }
    if ($fails -ge 5) {
        Write-Sup "5회 연속 빠른 크래시 — 60초 대기. 원인은 위 stderr 확인."
        Start-Sleep -Seconds 60
        $fails = 0
    } else {
        Start-Sleep -Seconds 3
    }
}
