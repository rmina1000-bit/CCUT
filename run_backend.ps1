$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER="T"
# [2026-07-04] 검증 확정 게이트 (run_backend_supervised.ps1과 동일)
$env:CCUT_HUB_PLAN="1"
$env:CCUT_AUTO_REINDEX="1"
$env:CCUT_SINGLE_CACHE="1"
$env:CCUT_LEGACY_NARRATIVE="0"
python ccut_backend/main.py
