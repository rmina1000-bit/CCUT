# ============================================================================
#  CCUT 1.0.4 STEP 8-9 GitHub Artifacts Cleanup — Single Commit Script
#  Target  : ccut-1.0.4-step9 branch (rmina1000-bit/CCUT)
#  Baseline: 43b040f2950c8c81bb0591a4ab93042cf320201f
#  Result  : One commit "Clean STEP 8-9 GitHub artifacts" pushed to origin
# ============================================================================

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Step($m){ Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Pass($m){ Write-Host "[OK]   $m" -ForegroundColor Green }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m){ Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

# ----- 0. cwd -----
Step "0. Working directory"
Set-Location "D:\CCUT1.0.4"
Pass "cwd = $((Get-Location).Path)"

# ----- 1. branch -----
Step "1. Branch verification"
$branch = (git branch --show-current).Trim()
if ($branch -ne "ccut-1.0.4-step9") {
    Fail "Expected branch 'ccut-1.0.4-step9', got '$branch'. Run: git checkout ccut-1.0.4-step9"
}
Pass "branch = $branch"

# ----- 2. remote -----
Step "2. Remote verification"
$origin = (git remote get-url origin).Trim()
if ($origin -notmatch "github\.com[:/]rmina1000-bit/CCUT(\.git)?$") {
    Fail "origin must be rmina1000-bit/CCUT. Got: '$origin'"
}
Pass "origin = $origin"

# ----- 3. HEAD sync -----
Step "3. HEAD sync check"
git fetch origin ccut-1.0.4-step9 2>&1 | Out-Null
$localHead  = (git rev-parse HEAD).Trim()
$remoteHead = (git rev-parse origin/ccut-1.0.4-step9).Trim()
$expected   = "43b040f2950c8c81bb0591a4ab93042cf320201f"
Write-Host "  local  HEAD = $localHead"
Write-Host "  remote HEAD = $remoteHead"
if ($localHead -ne $remoteHead) {
    Fail "Local HEAD != origin/ccut-1.0.4-step9. Run: git pull origin ccut-1.0.4-step9"
}
if ($localHead -eq $expected) { Pass "HEAD matches audit baseline 43b040f" }
else { Warn "HEAD ($localHead) is not 43b040f — proceeding anyway" }

# ----- 4. clean tree -----
Step "4. Working tree clean check"
$dirty = git status --porcelain
if ($dirty) { Write-Host $dirty; Fail "Working tree not clean. Commit or stash first." }
Pass "working tree clean"

# ----- 5..7. delete temp files / logs / archives -----
Step "5. Delete temp/log/archive paths"
$paths = @(
    # root temp scripts/artifacts
    "check_db.py","fix_mojibake.py","fix_mojibake_block.py","fix_mojibake_final.py",
    "proposal_request.json","step3_meta_check.json","step3_verify.json",
    "uploads_list.csv","verify_repair.ps1","verify_repair_output.txt",
    # backend temp/logs
    "ccut_backend/main.py.bak","ccut_backend/diff_main.txt","ccut_backend/full_diff.txt",
    "ccut_backend/backend.log","ccut_backend/backend_err.log",
    # tools log + bulk dirs
    "tools/test_vulkan.log",
    "ccut_backend/logs/hook_distribution",
    "_archive_backend_20260420"
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        if ((Get-Item $p).PSIsContainer) {
            git rm -r -f -- $p | Out-Null
            Pass "removed dir  $p"
        } else {
            git rm -f -- $p | Out-Null
            Pass "removed file $p"
        }
    } else {
        Warn "$p not found (skip)"
    }
}

# ----- 8. mojibake fix in Index.tsx -----
Step "8. Mojibake fix in Index.tsx"
$indexPath = "ccut_frontend/src/pages/Index.tsx"
if (-not (Test-Path $indexPath)) { Fail "$indexPath not found" }
$indexFull = (Resolve-Path $indexPath).Path
$content = [System.IO.File]::ReadAllText($indexFull, $utf8NoBom)

$pairs = @(
    @{ old = '"諛깆뿏??遺꾩꽍 湲곕컲 異붿쿇 ?몄쭛?덉엯?덈떎."';
       new = '"백엔드 분석 기반 추천 편집안입니다."' },
    @{ old = '"遺꾩꽍 以??ㅻ쪟媛 諛쒖깮?덉뒿?덈떎. 肄섏넄???뺤씤??二쇱꽭??"';
       new = '"분석 중 오류가 발생했습니다. 콘솔을 확인해 주세요."' },
    @{ old = '"[Reproposal] sourceFragments媛 ?놁뼱 ?ъ젣?덉쓣 嫄대꼫?곷땲??"';
       new = '"[Reproposal] sourceFragments가 없어 재제안을 건너뜁니다."' }
)
foreach ($p in $pairs) {
    if ($content.Contains($p.old)) {
        $content = $content.Replace($p.old, $p.new)
        Pass "replaced mojibake fragment"
    } else {
        Warn "pattern not found (already fixed?): $($p.old.Substring(0,[Math]::Min(40,$p.old.Length)))..."
    }
}
[System.IO.File]::WriteAllText($indexFull, $content, $utf8NoBom)

# verify (regex with alternation; SimpleMatch can't handle |)
$mojiHits = Select-String -Path $indexPath -Pattern '諛|遺|湲|꽍|깆|뿏|諛쒖|肄섏|嫄대' -Encoding UTF8
if ($mojiHits) { Warn "mojibake remnants:"; $mojiHits | ForEach-Object { Write-Host "  $_" } }
else { Pass "no mojibake markers in Index.tsx" }

# ----- 9. main.py legacy hardcoded path -----
Step "9. main.py D:/test_video.mp4 removal"
$mainPath = "ccut_backend/main.py"
$mainFull = (Resolve-Path $mainPath).Path
$mainContent = [System.IO.File]::ReadAllText($mainFull, $utf8NoBom)
$mainPairs = @(
    @{ old = 'async def analyze_video(video_path: str = "D:/test_video.mp4"):';
       new = 'async def analyze_video(video_path: str = ""):' },
    @{ old = 'async def smart_analyze_video(video_path: str = "D:/test_video.mp4"):';
       new = 'async def smart_analyze_video(video_path: str = ""):' }
)
foreach ($p in $mainPairs) {
    if ($mainContent.Contains($p.old)) {
        $mainContent = $mainContent.Replace($p.old, $p.new)
        Pass "replaced: $($p.old)"
    } else { Warn "not found (already fixed?): $($p.old)" }
}
[System.IO.File]::WriteAllText($mainFull, $mainContent, $utf8NoBom)
$dCheck = Select-String -Path $mainPath -Pattern 'D:/test_video\.mp4' -SimpleMatch
if ($dCheck) { Warn "remnant in main.py:"; $dCheck | ForEach-Object { Write-Host "  $_" } }
else { Pass "no D:/test_video.mp4 in main.py" }

# ----- 10. CenterPanel.tsx normalizeMediaUrl -----
Step "10. CenterPanel.tsx normalizeMediaUrl fix"
$centerPath = "ccut_frontend/src/components/CenterPanel.tsx"
$centerFull = (Resolve-Path $centerPath).Path
$cc = [System.IO.File]::ReadAllText($centerFull, $utf8NoBom)

$cPair1Old = 'if (url.startsWith("http")) return url;'
$cPair1New = 'if (url.startsWith("http://") || url.startsWith("https://")) return url;'
if ($cc.Contains($cPair1Old)) { $cc = $cc.Replace($cPair1Old, $cPair1New); Pass "http(s) check tightened" }
else { Warn "http check pattern not found (already fixed?)" }

# Note: the original line uses backtick template literal `http://localhost:8000${url}`
$cPair2Old = 'return `http://localhost:8000${url}`;'
$cPair2New = 'return `${videoService.API_BASE_URL}${url}`;'
if ($cc.Contains($cPair2Old)) { $cc = $cc.Replace($cPair2Old, $cPair2New); Pass "localhost:8000 -> videoService.API_BASE_URL" }
else { Warn "localhost:8000 pattern not found (already fixed?)" }

[System.IO.File]::WriteAllText($centerFull, $cc, $utf8NoBom)
$lhCheck = Select-String -Path $centerPath -Pattern 'localhost:8000' -SimpleMatch
if ($lhCheck) { Warn "localhost remnant:"; $lhCheck | ForEach-Object { Write-Host "  $_" } }
else { Pass "no localhost:8000 in CenterPanel.tsx" }

# Sanity: ensure videoService is imported
$hasImport = Select-String -Path $centerPath -Pattern 'videoService' -SimpleMatch | Select-Object -First 1
if (-not $hasImport) { Warn "videoService not imported in CenterPanel.tsx — add import manually before commit" }

# ----- 11. .gitignore augmentation -----
Step "11. .gitignore augmentation"
$giPath = ".gitignore"
$giFull = if (Test-Path $giPath) { (Resolve-Path $giPath).Path } else { (Join-Path (Get-Location) $giPath) }
$gi = if (Test-Path $giFull) { [System.IO.File]::ReadAllText($giFull, $utf8NoBom) } else { "" }
$rules = @("*.log","*.bak","**/logs/","diff_main.txt","full_diff.txt","verify_repair_output.txt")
$add = ""
foreach ($r in $rules) {
    if ($gi -notmatch ("(?m)^" + [Regex]::Escape($r) + "\s*$")) { $add += "$r`n" }
}
if ($add) {
    if (-not $gi.EndsWith("`n")) { $gi += "`n" }
    $gi += "`n# === STEP 8-9 hygiene additions ===`n" + $add
    [System.IO.File]::WriteAllText($giFull, $gi, $utf8NoBom)
    Pass ".gitignore augmented"
} else { Pass ".gitignore already complete" }

# ----- 12. optional builds -----
Step "12. Optional verification builds"
if (Test-Path "ccut_frontend/package.json") {
    Push-Location "ccut_frontend"
    if (Test-Path "node_modules") {
        Write-Host "  npm run build ..."
        npm run build 2>&1 | Out-Host
        if ($LASTEXITCODE -eq 0) { Pass "npm run build OK" } else { Warn "npm run build failed (continuing)" }
    } else { Warn "node_modules missing — skip npm build" }
    Pop-Location
} else { Warn "ccut_frontend/package.json missing — skip" }

if (Get-Command python -ErrorAction SilentlyContinue) {
    Push-Location "ccut_backend"
    python -m py_compile main.py
    if ($LASTEXITCODE -eq 0) { Pass "main.py py_compile OK" } else { Warn "main.py py_compile FAILED" }
    python -m py_compile engine/render_engine.py
    if ($LASTEXITCODE -eq 0) { Pass "render_engine.py py_compile OK" } else { Warn "render_engine.py py_compile FAILED" }
    Pop-Location
} else { Warn "python not on PATH — skip py_compile" }

# ----- 13. stage + status -----
Step "13. Stage and status"
git add -A
$short = git status --short
Write-Host $short
$staged = git diff --cached --name-only
if (-not $staged) { Fail "Nothing staged — script may have produced no changes." }

# ----- 14. single commit -----
Step "14. Single commit"
git commit -m "Clean STEP 8-9 GitHub artifacts"
if ($LASTEXITCODE -ne 0) { Fail "git commit failed" }
$newHead = (git rev-parse HEAD).Trim()
if ($newHead -eq $localHead) { Fail "HEAD did not advance" }
Pass "new HEAD = $newHead"

# ----- 15. push -----
Step "15. Push to origin"
git push origin ccut-1.0.4-step9
if ($LASTEXITCODE -ne 0) { Fail "git push failed" }

# ----- 16. final sync verify -----
Step "16. Verify remote sync"
git fetch origin ccut-1.0.4-step9 2>&1 | Out-Null
$remoteFinal = (git rev-parse origin/ccut-1.0.4-step9).Trim()
Write-Host "  local  HEAD = $newHead"
Write-Host "  remote HEAD = $remoteFinal"
if ($newHead -ne $remoteFinal) { Fail "local != remote after push" }
Pass "PUSH CONFIRMED — local and remote at $newHead"

# ----- 17. final report -----
Step "DONE"
Write-Host @"

==============================================================
  CCUT 1.0.4 STEP 8-9 cleanup — SUCCESS
==============================================================
  branch     : ccut-1.0.4-step9
  old HEAD   : $localHead
  new HEAD   : $newHead
  commit msg : Clean STEP 8-9 GitHub artifacts
  push       : OK (origin = $remoteFinal)
==============================================================

Report this new HEAD SHA back to Claude Code for the 4th audit.
"@
