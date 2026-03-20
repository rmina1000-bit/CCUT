param(
  [string]$BaseUrl = "http://127.0.0.1:4173"
)

$ErrorActionPreference = "Stop"

$uiRoot = Split-Path -Parent $PSScriptRoot
$qaDir = Join-Path $uiRoot ".qa"
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$profileDir = Join-Path $qaDir "chrome-interaction-basic-$timestamp"
$targetUrl = "$BaseUrl/interaction-basic.html?ts=$timestamp"

New-Item -ItemType Directory -Force -Path $qaDir | Out-Null

if (!(Test-Path $chromePath)) {
  throw "Chrome not found at $chromePath"
}

try {
  Invoke-WebRequest -UseBasicParsing $targetUrl | Out-Null
} catch {
  throw "Interaction runner is not reachable at $targetUrl. Start the dev server first."
}

$process = Start-Process -FilePath $chromePath -ArgumentList "--disable-extensions --user-data-dir=`"$profileDir`" --window-size=1400,1100 --app=`"$targetUrl`"" -PassThru

$deadline = (Get-Date).AddSeconds(45)
$runnerWindow = $null

do {
  $runnerWindow = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like 'CCUT Interaction Basic Spec Runner | *'
  } | Sort-Object StartTime -Descending | Select-Object -First 1

  if ($runnerWindow) {
    break
  }

  Start-Sleep -Milliseconds 750
} while ((Get-Date) -lt $deadline)

if ($process -and !$process.HasExited) {
  Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}

if (!$runnerWindow) {
  throw "Interaction runner did not reach a final titled result before timeout."
}

$result = @{
  targetUrl = $targetUrl
  windowTitle = $runnerWindow.MainWindowTitle
}

Write-Output ($result | ConvertTo-Json)
