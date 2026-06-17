# Weekday 7:45 AM scan (uses PC local timezone — set Windows to Mountain for MST/MDT).
$TaskName = "StockScannerMorning"
$ProjectRoot = "C:\Users\Macra\OneDrive\Desktop\stockscanner"
$Batch = Join-Path $ProjectRoot "scripts\run-scheduled.bat"

$action = New-ScheduledTaskAction -Execute $Batch -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "7:45AM"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Stock scanner: weekday scan + Discord alert at 7:45 AM local (Mountain)" `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' updated: Mon-Fri at 7:45 AM (local PC time)" -ForegroundColor Green
Write-Host "Logs: $ProjectRoot\data\logs\"
Write-Host ""
Write-Host "Verify: Task Scheduler -> Task Scheduler Library -> $TaskName"
Write-Host "Test now: schtasks /Run /TN $TaskName"
