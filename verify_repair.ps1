# 1. First Upload
$resp1 = Invoke-RestMethod -Uri "http://localhost:8000/generate-fragments?video_path=D:\CCUT1.0.4\ccut_backend\storage\uploads\20130512_143229.mp4" -Method Post
$sid1 = $resp1.source_id
Write-Host "Initial Source ID: $sid1"

# 2. Duplicate Upload
$resp2 = Invoke-RestMethod -Uri "http://localhost:8000/generate-fragments?video_path=D:\CCUT1.0.4\ccut_backend\storage\uploads\20130512_143229.mp4" -Method Post
$sid2 = $resp2.source_id
Write-Host "Secondary Source ID: $sid2"

Start-Sleep -Seconds 50

# 3. Meta Check
$frags = Invoke-RestMethod -Uri "http://localhost:8000/fragments/$sid1"
$frags.fragments[0].intelligence | Select-Object start_frame, end_frame, _proxy_video_path | Format-Table | Out-String | Write-Host

# 4. Evidence Check
$ev = Invoke-RestMethod -Uri "http://localhost:8000/evidence/$sid1"
Write-Host "Coverage: $($ev.coverage)"
$ev.evidence | Select-Object start, end, text, audio_energy, confidence | Format-Table -AutoSize | Out-String | Write-Host

# 5. Quick Scan Check
$qs = Invoke-RestMethod -Uri "http://localhost:8000/quick-scan/$sid1"
$qs | ConvertTo-Json -Depth 5 | Write-Host
