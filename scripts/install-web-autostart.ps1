# Starts web dashboard at Windows logon (enables 7:30 AM auto-scan).
$TaskName = "StockScannerWeb"
$ProjectRoot = "C:\Users\Macra\OneDrive\Desktop\stockscanner"
$Batch = Join-Path $ProjectRoot "scripts\start-web-background.bat"

@'
@echo off
cd /d "C:\Users\Macra\OneDrive\Desktop\stockscanner"
start "StockScannerWeb" /MIN cmd /c ".venv\Scripts\python.exe -m stockscanner web"
'@ | Set-Content -Path $Batch -Encoding ASCII

$action = New-ScheduledTaskAction -Execute $Batch -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Start Stock Scanner web dashboard at logon (7:30 AM Mountain auto-scan)" `
    -Force | Out-Null

Write-Host "Task '$TaskName' created - web dashboard starts at logon" -ForegroundColor Green
Write-Host "Open: http://127.0.0.1:8787"
