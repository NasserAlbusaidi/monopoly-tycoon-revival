# Builds harness.exe (x86) next to the shim in src\mtrevival\bin\ — it is a
# test tool, not package data (the wheel only picks up *.dll).
#   pwsh tools\wmsource-shim\build-harness.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $here '..\..')).Path
$out = Join-Path $root 'src\mtrevival\bin'
New-Item -ItemType Directory -Force $out | Out-Null

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'MSVC Build Tools not found (vswhere returned nothing).' }
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars32.bat'

$obj = Join-Path $env:TEMP 'wmsource-shim-build'
New-Item -ItemType Directory -Force $obj | Out-Null
$exe = Join-Path $out 'harness.exe'
cmd /c "call `"$vcvars`" >nul 2>&1 && cd /d `"$obj`" && cl /nologo /W4 /O1 /MT /EHsc /Fe:`"$exe`" `"$here\harness.cpp`""
if ($LASTEXITCODE -ne 0) { throw "cl failed with exit code $LASTEXITCODE" }
Get-Item $exe | Select-Object FullName, Length
