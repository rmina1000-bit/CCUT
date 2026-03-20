param(
  [string]$BaseUrl = "http://127.0.0.1:4173"
)

$ErrorActionPreference = "Stop"

$uiRoot = Split-Path -Parent $PSScriptRoot
$qaDir = Join-Path $uiRoot ".qa"
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$profileDir = Join-Path $qaDir "chrome-browser-sanity-$timestamp"
$domPath = Join-Path $qaDir "browser-sanity.dom.html"
$screenshotPath = Join-Path $qaDir "browser-sanity.png"
$targetUrl = "$BaseUrl/browser-sanity.html?ts=$timestamp"

New-Item -ItemType Directory -Force -Path $qaDir | Out-Null

if (!(Test-Path $chromePath)) {
  throw "Chrome not found at $chromePath"
}

try {
  Invoke-WebRequest -UseBasicParsing $targetUrl | Out-Null
} catch {
  throw "Browser sanity runner is not reachable at $targetUrl. Start the dev server first."
}

$dom = (& $chromePath --headless=new --disable-gpu --virtual-time-budget=12000 --user-data-dir="$profileDir" --dump-dom "$targetUrl" 2>&1 | Out-String)
$dom | Set-Content -Path $domPath -Encoding UTF8

& $chromePath --headless=new --disable-gpu --window-size=1440,1024 --user-data-dir="$profileDir" --screenshot="$screenshotPath" "$targetUrl" | Out-Null

if (!(Test-Path $screenshotPath)) {
  throw "Browser sanity screenshot was not created."
}

$match = [regex]::Match($dom, '<script id="browser-sanity-json" type="application/json">(?s)(.*?)</script>')
if (!$match.Success) {
  throw "Could not locate browser sanity JSON in dumped DOM."
}

$result = $match.Groups[1].Value | ConvertFrom-Json
$result | Add-Member -NotePropertyName domPath -NotePropertyValue $domPath
$result | Add-Member -NotePropertyName screenshotPath -NotePropertyValue $screenshotPath

$json = $result | ConvertTo-Json -Depth 8
Write-Output $json

if (-not $result.pass) {
  exit 1
}
