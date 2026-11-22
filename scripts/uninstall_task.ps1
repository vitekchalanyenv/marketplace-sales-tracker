# Removes the daily agent from Windows Task Scheduler.
$ErrorActionPreference = "Stop"
$TaskName = "marketplace-sales-tracker"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Task '$TaskName' removed."
} else {
    Write-Host "Task '$TaskName' is not registered."
}
