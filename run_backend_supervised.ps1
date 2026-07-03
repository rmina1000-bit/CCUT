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

# [2026-07-04] 검증 확정 게이트 — supervisor 경유 기동에서도 동일 적용
# (미설정 시 hub plan/캐시/게이트가 전부 꺼진 옛 경로로 뜸)
$env:CCUT_HUB_PLAN         = "1"
$env:CCUT_AUTO_REINDEX     = "1"
$env:CCUT_SINGLE_CACHE     = "1"
$env:CCUT_LEGACY_NARRATIVE = "0"
# 신규 기능 게이트는 검증 전까지 기본 OFF: CCUT_REVISION / CCUT_QUALITY_LOG /
# CCUT_PERSON_REQUERY / CCUT_JUDGE_PARALLEL (병렬화는 실측 FAIL로 비활성 유지)

function Write-Sup($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $SupLog -Value $line -Encoding utf8
}

# 14일 지난 로그 정리
Get-ChildItem $LogDir -Filter "backend_*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 이미 떠 있으면 중복 기동 방지
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Sup "8000 already listening (pid=$($existing.OwningProcess)). supervisor exit."
    exit 0
}

Write-Sup "=== supervisor start ==="
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
