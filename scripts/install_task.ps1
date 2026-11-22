# Registers the daily agent in Windows Task Scheduler (spec docs/spec/M5-denni-agent.md).
# Runs every day at 08:00; if the PC was off, as soon as possible after logon (StartWhenAvailable).
# Only while the user is logged on: Chrome needs the user's profile for Cosmos.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 [-At 08:00]
param([string]$At = "08:00")

$ErrorActionPreference = "Stop"
$TaskName = "marketplace-sales-tracker"
$Root = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) { throw "Missing $Pythonw - run 'uv sync' first." }

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-m sales_tracker run daily" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Daily sales sync (Gumroad, Cosmos, Fab) with a morning report e-mail." -Force | Out-Null

Write-Host "Task '$TaskName' registered: daily at $At, catches up after the PC is turned on."
Write-Host "Run it now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Logs: data\private\logs\"
