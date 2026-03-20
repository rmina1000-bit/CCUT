param(
  [string]$BaseUrl = "http://127.0.0.1:4173"
)

$ErrorActionPreference = "Stop"

$uiRoot = Split-Path -Parent $PSScriptRoot
$qaDir = Join-Path $uiRoot ".qa"
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
$profileDir = Join-Path $qaDir "chrome-component-smoke-$timestamp"
$domPath = Join-Path $qaDir "component-smoke.dom.html"
$targetUrl = "$BaseUrl/component-smoke.html?ts=$timestamp"

New-Item -ItemType Directory -Force -Path $qaDir | Out-Null

if (!(Test-Path $chromePath)) {
  throw "Chrome not found at $chromePath"
}

try {
  Invoke-WebRequest -UseBasicParsing $targetUrl | Out-Null
} catch {
  throw "Component smoke runner is not reachable at $targetUrl. Start the dev server first."
}

$dom = (& $chromePath --headless=new --disable-gpu --virtual-time-budget=12000 --user-data-dir="$profileDir" --dump-dom "$targetUrl" 2>&1 | Out-String)
$dom | Set-Content -Path $domPath -Encoding UTF8

$match = [regex]::Match($dom, '<script id="component-smoke-json" type="application/json">(?s)(.*?)</script>')
if (!$match.Success) {
  throw "Could not locate component smoke JSON in dumped DOM."
}

$result = $match.Groups[1].Value | ConvertFrom-Json
$result | Add-Member -NotePropertyName domPath -NotePropertyValue $domPath

$json = $result | ConvertTo-Json -Depth 8
Write-Output $json

if (-not $result.pass) {
  exit 1
}
