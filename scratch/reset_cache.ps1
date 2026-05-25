# 1) 서버 종료
$ports = @(8000,8080,8081)
foreach ($p in $ports) {
  $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
  }
}

# 2) DB 백업
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item "ccut_backend\ccut_app.db" "ccut_backend\ccut_app.backup_before_cache_clear_$ts.db" -ErrorAction SilentlyContinue

# 3) 분석 산출 파일 캐시 삭제
$cacheDirs = @(
  "storage\fragments",
  "storage\thumbnails",
  "storage\panorama",
  "storage\proxies",
  "storage\proposal_previews",
  "storage\exports",
  "ccut_backend\storage\fragments",
  "ccut_backend\storage\thumbnails",
  "ccut_backend\storage\panorama",
  "ccut_backend\storage\proxies",
  "ccut_backend\storage\proposal_previews",
  "ccut_backend\storage\exports"
)

foreach ($dir in $cacheDirs) {
  if (Test-Path $dir) {
    Get-ChildItem $dir -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[CLEARED] $dir"
  }
}

# 4) DB 분석 테이블 초기화 — 원본 파일은 삭제하지 않음
python - <<'PY'
import sqlite3
from pathlib import Path

db = Path("ccut_backend/ccut_app.db")
conn = sqlite3.connect(db)
cur = conn.cursor()

tables = [
    "export_results",
    "export_input",
    "proposals",
    "semantic_fragments",
    "evidence_board",
    "fragments",
    "user_intents",
    "sources"
]

existing = {
    r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
}

for t in tables:
    if t in existing:
        cur.execute(f"DELETE FROM {t}")
        print(f"[DB CLEARED] {t}")

conn.commit()
conn.close()
print("[DONE] analysis cache cleared. uploads/original files preserved.")
PY

# 5) 확인
git status --short
Write-Host "분석 캐시 초기화 완료. 원본 영상 uploads 폴더는 보존했습니다."
