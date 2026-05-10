# ============================================================
# CCUT faststart repair script
# 목적: moov atom을 파일 앞으로 이동 (-movflags +faststart)
# 방법: -c copy (re-encode 없음)
# ffmpeg: C:\Users\rmina\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe
# ============================================================

$uploads = "D:\CCUT1.0.4\storage\uploads"
$logFile = "D:\CCUT1.0.4\storage\faststart_repair.log"
$ffmpeg  = "ffmpeg"   # PATH에서 해결됨

"[faststart_repair] 시작: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Tee-Object -FilePath $logFile

$files = Get-ChildItem "$uploads\*" -Include "*.mp4","*.MOV" -File | Sort-Object Length
$total  = $files.Count
$ok     = 0
$fail   = 0

"총 $total 개 파일 처리 시작`n" | Tee-Object -FilePath $logFile -Append

foreach ($f in $files) {
    $out    = Join-Path $uploads "_tmp_fs_$($f.Name)"
    $sizeMB = [math]::Round($f.Length / 1MB, 1)
    $idx    = $ok + $fail + 1

    "[{0}/{1}] {2} ({3}MB)" -f $idx, $total, $f.Name, $sizeMB | Tee-Object -FilePath $logFile -Append

    # 기존 임시 파일 정리
    if (Test-Path $out) { Remove-Item $out -Force }

    $t0  = Get-Date
    # & 연산자로 직접 호출 (Start-Process보다 안정적)
    & $ffmpeg -y -loglevel error `
        -i $f.FullName `
        -c copy `
        -movflags +faststart `
        $out 2>&1 | Out-Null
    $rc  = $LASTEXITCODE
    $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)

    $outOk = (Test-Path $out) -and ((Get-Item $out).Length -gt 10240)

    if ($rc -eq 0 -and $outOk) {
        Move-Item $out $f.FullName -Force
        $ok++
        "  OK  ({0}s)" -f $sec | Tee-Object -FilePath $logFile -Append
    } else {
        $fail++
        "  FAIL (exit={0}, elapsed={1}s)" -f $rc, $sec | Tee-Object -FilePath $logFile -Append
        if (Test-Path $out) { Remove-Item $out -Force }
    }
}

"`n[faststart_repair] 완료: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Tee-Object -FilePath $logFile -Append
"성공: $ok / $total   실패: $fail" | Tee-Object -FilePath $logFile -Append
