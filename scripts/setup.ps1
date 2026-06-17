# Run from project folder. Creates Desktop launchers + optional scheduled task.

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DesktopLauncherDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "Stock Scanner"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Pip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

Write-Host ""
Write-Host "=== Stock Scanner Setup ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

# --- Python venv ---
if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $Pip install -r (Join-Path $ProjectRoot "requirements.txt") -q

# --- Discord webhook ---
$EnvFile = Join-Path $ProjectRoot ".env"
$ExampleFile = Join-Path $ProjectRoot ".env.example"

Write-Host ""
Write-Host "--- Discord webhook (one-time) ---" -ForegroundColor Cyan
Write-Host "1. Open Discord -> your server -> Server Settings"
Write-Host "2. Integrations -> Webhooks -> New Webhook"
Write-Host "3. Name it 'Stock Scanner', pick a channel, Save"
Write-Host "4. Click 'Copy Webhook URL'"
Write-Host ""

$existing = ""
if (Test-Path $EnvFile) {
    $lines = Get-Content $EnvFile
    foreach ($line in $lines) {
        if ($line -match "^DISCORD_WEBHOOK_URL=(.+)$") {
            $existing = $Matches[1].Trim()
            break
        }
    }
}

if ($existing -and $existing -notmatch "YOUR_ID") {
    Write-Host "Found existing webhook in .env" -ForegroundColor Green
    $useExisting = Read-Host "Keep it? (Y/n)"
    if ($useExisting -eq "" -or $useExisting -eq "Y" -or $useExisting -eq "y") {
        $webhook = $existing
    } else {
        $webhook = Read-Host "Paste Discord webhook URL"
    }
} else {
    $webhook = Read-Host "Paste Discord webhook URL (or press Enter to skip for now)"
}

if ($webhook) {
    $content = @"
# Discord alerts
DISCORD_WEBHOOK_URL=$webhook

# Email (optional - leave blank to use Discord only)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_TO=
SMTP_USE_TLS=true
"@
    Set-Content -Path $EnvFile -Value $content -Encoding UTF8
    Write-Host "Saved .env" -ForegroundColor Green

    Write-Host "Testing Discord alert..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    & $Python -m stockscanner alert-test
    Pop-Location
} else {
    if (-not (Test-Path $EnvFile)) {
        Copy-Item $ExampleFile $EnvFile
        Write-Host "Copied .env.example -> .env (fill in webhook later)" -ForegroundColor Yellow
    }
}

# --- Desktop launchers ---
New-Item -ItemType Directory -Force -Path $DesktopLauncherDir | Out-Null

function Write-Launcher($Name, $Args) {
    $bat = Join-Path $DesktopLauncherDir "$Name.bat"
    @"
@echo off
title Stock Scanner - $Name
cd /d "$ProjectRoot"
call "$ProjectRoot\.venv\Scripts\activate.bat"
python -m stockscanner $Args
echo.
pause
"@ | Set-Content -Path $bat -Encoding ASCII
    Write-Host "Created: $bat" -ForegroundColor Green
}

Write-Launcher "Run Scan (with Discord alert)" "scan --alert"
Write-Launcher "Check Market Regime" "regime"
Write-Launcher "Test Discord Alert" "alert-test"
Write-Launcher "Run Scan (no alert)" "scan"

# --- Optional scheduled task ---
Write-Host ""
$schedule = Read-Host "Schedule weekday scan at 4:30 PM? (y/N)"
if ($schedule -eq "y" -or $schedule -eq "Y") {
    $taskName = "StockScannerDaily"
    $action = New-ScheduledTaskAction -Execute $Python -Argument "-m stockscanner scan --alert" -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "4:30PM"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled task '$taskName' created (Mon-Fri 4:30 PM)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done! Double-click launchers in:" -ForegroundColor Cyan
Write-Host "  $DesktopLauncherDir"
Write-Host ""
