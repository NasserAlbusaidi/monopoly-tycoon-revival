# Builds dist\MonopolyTycoonFix.exe: one file, console, no Python needed on
# the player's machine. The music shim must already be built
# (tools\wmsource-shim\build.ps1) so it can be bundled.
#   pwsh tools\exe\build-exe.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..\..')).Path
$shim = Join-Path $root 'src\mtrevival\bin\wmsource-shim.dll'
if (-not (Test-Path $shim)) { throw "missing $shim - run tools\wmsource-shim\build.ps1 first" }

$python = if (Test-Path (Join-Path $root '.venv\Scripts\python.exe')) { Join-Path $root '.venv\Scripts\python.exe' } else { 'python' }
& $python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller is not installed: python -m pip install pyinstaller' }

$work = Join-Path $env:TEMP 'mtrevival-exe-build'
& $python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MonopolyTycoonFix `
    --distpath (Join-Path $root 'dist') `
    --workpath $work `
    --specpath $work `
    --paths (Join-Path $root 'src') `
    --collect-submodules mtrevival `
    --add-data "$shim;mtrevival\bin" `
    (Join-Path $here 'entry.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Get-Item (Join-Path $root 'dist\MonopolyTycoonFix.exe') | Select-Object FullName, Length
