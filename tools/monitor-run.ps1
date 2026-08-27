<#
.SYNOPSIS
Launch an executable and log every process it spawns and every dialog it shows.

.DESCRIPTION
Used to capture what a 2001 installer actually does on Windows 11: the full
process chain with command lines, and the exact text of every visible dialog
(title, static text, button labels). Run it from an elevated shell when the
target elevates, so the child inherits the token and its windows are readable.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File tools\monitor-run.ps1 `
  -Exe "D:\media\Extras\Patch\MTPatch1_2.exe" -Log patch-run.log
#>
param(
  [Parameter(Mandatory)] [string] $Exe,
  [string] $Log = "monitor-run.log",
  [int] $TimeoutMinutes = 10,
  [int] $IdleSeconds = 8
)
$ErrorActionPreference = 'Continue'

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class MonitorWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessageTimeout(IntPtr h, uint msg, IntPtr w, StringBuilder l, uint flags, uint t, out IntPtr r);
  static string Text(IntPtr h) { var sb = new StringBuilder(4096); IntPtr r; SendMessageTimeout(h, 0x000D, (IntPtr)4096, sb, 2, 200, out r); return sb.ToString(); }
  static string Cls(IntPtr h) { var sb = new StringBuilder(256); GetClassName(h, sb, 256); return sb.ToString(); }
  public static List<string> Snapshot(HashSet<uint> pids) {
    var outl = new List<string>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (!pids.Contains(pid)) return true;
      var t = new StringBuilder(512); GetWindowText(h, t, 512);
      var sb = new StringBuilder("WIN pid=" + pid + " cls=" + Cls(h) + " title=[" + t + "]");
      EnumChildWindows(h, (c, l2) => {
        string cc = Cls(c); string ct = Text(c);
        if (ct.Length > 0 && (cc == "Static" || cc == "Button" || cc == "Edit" || cc.StartsWith("RichEdit")))
          sb.Append(" | " + cc + ":[" + ct.Replace("\r\n", " / ") + "]");
        return true;
      }, IntPtr.Zero);
      outl.Add(sb.ToString());
      return true;
    }, IntPtr.Zero);
    return outl;
  }
}
"@

$elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')
"=== monitor start $(Get-Date -Format o) elevated=$elevated exe=$Exe" | Set-Content $Log

$known = @{}
Get-CimInstance Win32_Process | ForEach-Object { $known[[int]$_.ProcessId] = $true }

$p = Start-Process -FilePath $Exe -WorkingDirectory (Split-Path $Exe) -PassThru
$tree = @{ [int]$p.Id = $true }
"LAUNCH pid=$($p.Id)" | Add-Content $Log

$seen = @{}
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$idleSince = $null
while ((Get-Date) -lt $deadline) {
  $procs = Get-CimInstance Win32_Process
  $alive = @{}
  # two passes so a grandchild seen before its parent is still attached
  foreach ($pass in 1..2) {
    foreach ($q in $procs) {
      $pid_ = [int]$q.ProcessId; $ppid_ = [int]$q.ParentProcessId
      $alive[$pid_] = $true
      if ($tree.ContainsKey($ppid_) -and -not $tree.ContainsKey($pid_)) { $tree[$pid_] = $true }
    }
  }
  foreach ($q in $procs) {
    $pid_ = [int]$q.ProcessId
    if ($tree.ContainsKey($pid_) -and -not $known.ContainsKey($pid_)) {
      $known[$pid_] = $true
      "$(Get-Date -Format HH:mm:ss.fff) PROC pid=$pid_ ppid=$($q.ParentProcessId) name=$($q.Name) path=[$($q.ExecutablePath)] cmd=[$($q.CommandLine)]" | Add-Content $Log
    }
  }
  $pids = New-Object 'System.Collections.Generic.HashSet[uint32]'
  foreach ($k in $tree.Keys) { [void]$pids.Add([uint32]$k) }
  foreach ($line in [MonitorWin]::Snapshot($pids)) {
    if (-not $seen.ContainsKey($line)) { $seen[$line] = $true; "$(Get-Date -Format HH:mm:ss.fff) $line" | Add-Content $Log }
  }
  $treeAlive = $false
  foreach ($k in @($tree.Keys)) { if ($alive.ContainsKey($k)) { $treeAlive = $true; break } }
  if ($treeAlive) { $idleSince = $null }
  elseif ($null -eq $idleSince) { $idleSince = Get-Date }
  elseif (((Get-Date) - $idleSince).TotalSeconds -gt $IdleSeconds) { break }
  Start-Sleep -Milliseconds 250
}
"=== monitor end $(Get-Date -Format o)" | Add-Content $Log
