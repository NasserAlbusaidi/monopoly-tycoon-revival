# Regenerates the harness fixtures: two 3-second mono sine tones encoded as
# WMA (wmav2) with ffmpeg. They are synthesised here, not game content, which
# is why .gitignore lets these two .wma files in.
#   pwsh tools\wmsource-shim\harness\make-fixtures.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpeg) { throw 'ffmpeg not on PATH' }
foreach ($tone in @(@{ name = 'tone-a'; hz = 440 }, @{ name = 'tone-b'; hz = 660 })) {
    & ffmpeg -v error -y -f lavfi -i "sine=frequency=$($tone.hz):sample_rate=44100:duration=3" `
        -c:a wmav2 -b:a 48k -ac 1 (Join-Path $here "$($tone.name).wma")
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed for $($tone.name)" }
}
Get-ChildItem (Join-Path $here '*.wma') | Select-Object Name, Length
