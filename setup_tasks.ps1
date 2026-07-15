<#
.SYNOPSIS
DailyDigest scheduled-task provisioning (F1a-2 — replaces setup_tasks.bat).

Registers the four tasks the way the 2026-07 accrual week proved they must be
registered — none of which `schtasks` can do:
  - WakeToRun + StartWhenAvailable + RunOnlyIfNetworkAvailable (the three
    settings that made the week survivable; applied by hand back then)
  - Run whether the user is logged on or not, with NO console window
    (interactive tasks pop a killable cmd window — a run died at 6s on 7/06)
    via an S4U principal (no password stored)
  - RunLevel Limited (the jobs need no elevation; /RL HIGHEST broke
    non-elevated registration for no benefit)
  - A 3h execution time limit on the run-once jobs (a hung run gets killed;
    the 9 AM Watchdog task then reports it) — NO limit on the ReplyMonitor
    daemon, which is supposed to run forever.

Tasks: MorningDigest 08:00, Watchdog 09:00 (O2: run_alert --check-completed),
MiddayAlert 13:00 (all Mon-Fri), ReplyMonitor at startup.

Also sets DIGEST_UNATTENDED=1 machine-wide (F1a-1) so a dead Gmail token
fails fast instead of hanging on a browser consent.

.NOTES
Run AS ADMINISTRATOR on the server, from the repo directory:
    powershell -ExecutionPolicy Bypass -File .\setup_tasks.ps1
    powershell -ExecutionPolicy Bypass -File .\setup_tasks.ps1 -DryRun
Verify afterwards:  Get-ScheduledTask -TaskPath "\DailyDigest\"

If S4U registration fails on the server (it can with AzureAD-joined accounts),
fall back to a stored-password principal — replace the $principal line with:
    $cred = Get-Credential $user
    ...and register with -User $user -Password $cred.GetNetworkCredential().Password
    instead of -Principal (same run-whether-logged-on behavior, password stored by
    the Task Scheduler service).
#>
param(
    [switch]$DryRun,
    [string]$RepoPath = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
$taskPath = "\DailyDigest\"
$user = "$env:USERDOMAIN\$env:USERNAME"
$weekdays = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"

# S4U = "run whether user is logged on or not" WITHOUT storing a password.
# Session-0 execution means no console window a user could close mid-run.
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited

$runOnceSettings = New-ScheduledTaskSettingsSet `
    -WakeToRun -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

# The reply monitor is a daemon: no time limit (0 disables), no WakeToRun
# (it starts at boot, not on a wall-clock trigger).
$daemonSettings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

$tasks = @(
    @{ Name = "MorningDigest"; Bat = "run_digest.bat"
       Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At 08:00
       Settings = $runOnceSettings },
    @{ Name = "Watchdog"; Bat = "run_watchdog.bat"
       Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At 09:00
       Settings = $runOnceSettings },
    @{ Name = "MiddayAlert"; Bat = "run_midday.bat"
       Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At 13:00
       Settings = $runOnceSettings },
    @{ Name = "ReplyMonitor"; Bat = "run_reply_monitor.bat"
       Trigger = New-ScheduledTaskTrigger -AtStartup
       Settings = $daemonSettings }
)

Write-Host "DailyDigest task provisioning (repo: $RepoPath; principal: $user, S4U)"
if ($DryRun) { Write-Host "-- DRY RUN: nothing will be registered or set --" }

foreach ($t in $tasks) {
    $batPath = Join-Path $RepoPath $t.Bat
    if (-not (Test-Path $batPath)) { throw "Missing wrapper: $batPath" }
    $action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $RepoPath

    if ($DryRun) {
        $trig = if ($t.Trigger.StartBoundary) {
            "weekly Mon-Fri at $([datetime]$t.Trigger.StartBoundary | Get-Date -Format HH:mm)"
        } else { "at startup" }
        Write-Host ("  would register {0}{1}: {2} ({3})" -f $taskPath, $t.Name, $batPath, $trig)
        continue
    }

    Register-ScheduledTask -TaskName $t.Name -TaskPath $taskPath `
        -Action $action -Trigger $t.Trigger -Principal $principal `
        -Settings $t.Settings -Force | Out-Null
    Write-Host "  registered $taskPath$($t.Name)"
}

if ($DryRun) {
    Write-Host "  would set machine env var DIGEST_UNATTENDED=1 (F1a-1 fail-fast consent guard)"
} else {
    [Environment]::SetEnvironmentVariable("DIGEST_UNATTENDED", "1", "Machine")
    Write-Host "  set machine env var DIGEST_UNATTENDED=1 (F1a-1 fail-fast consent guard)"
    Write-Host ""
    Write-Host "Done. Verify with: Get-ScheduledTask -TaskPath '$taskPath'"
    Write-Host "Reminder: other env vars (keys, DIGEST_TO if any) belong in env.bat or the"
    Write-Host "machine environment; the Gmail OAuth app must be in 'production' status."
}
