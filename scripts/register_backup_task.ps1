# Registers the daily DB backup for this Windows user (manuals/operations/postgres_backup_runbook.md).
# Runs scripts/backup_postgres.py "backup --auto" every day at 12:00. If the PC was off at that time,
# Windows runs it at the next start. Runs only while this user is logged on, so it can read the
# stored URL from Credential Manager and show a notification. No administrator rights are needed.
# The connection URL is never passed here; register it first with "backup_postgres.py store-credential".
param(
    [string]$Python = (Join-Path $env:USERPROFILE "anaconda3\pythonw.exe")
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Python)) {
    throw "pythonw.exe not found: $Python  (pass -Python <path to pythonw.exe>)"
}
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo "scripts\backup_postgres.py"
$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`" backup --auto" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At "12:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "GemDiceBot DB backup" -Description "GemDiceBot daily PostgreSQL backup (scripts/backup_postgres.py)" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered task 'GemDiceBot DB backup' (daily 12:00, catch up at next start)."
Write-Host "Check later with: python scripts\backup_postgres.py status"
