# run_weekly_update.ps1
# Weekly BBG snapshot refresh, driven by Windows Task Scheduler (Fri ~4:30pm ET).
#
# Steps:
#   1. Verify the Bloomberg Terminal is connected. If not, log and SKIP (exit 0)
#      so we never commit an empty/garbage snapshot.
#   2. python scripts\pull_earnings.py    -> earnings calendar + consensus JSON
#   3. python scripts\pull_estimates.py   -> estimate histories CSV (chains pull_prices.py)
#   4. Commit & push only output/snapshots (matches the repo's snapshot-commit convention).
#
# Each run appends to output\logs\weekly_update_<timestamp>.log.
# Native exit codes are checked explicitly; warnings on stderr are merged into
# the log and do not abort the run.

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\AdrianOw\Projects\BBG'
Set-Location $repo

$logDir = Join-Path $repo 'output\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("weekly_update_{0}.log" -f (Get-Date -Format 'yyyy-MM-dd_HHmmss'))

function Log($msg) {
    "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg | Tee-Object -FilePath $log -Append
}

Log "=== Weekly BBG update starting ==="

# The Python pull scripts report their own status via scripts\_hub_reporting.py,
# but a run that skips before they start reported nothing at all -- so the hub
# kept showing the prior week's green "success" while the site went stale.
# Anything that ends the run early has to report for itself.
$hubDir = $env:AUTOMATION_HUB_DIR
if (-not $hubDir) { $hubDir = 'C:\Users\AdrianOw\Projects\automation-hub' }

function Send-HubReport($status, $message) {
    Push-Location $hubDir
    try {
        python -m scripts.hub_report bbg --status $status --message $message 2>&1 |
            Tee-Object -FilePath $log -Append
    } catch {
        # Reporting must never mask the run's own result.
        Log "hub_report failed: $_"
    } finally {
        Pop-Location
    }
}

# 1) Bloomberg connectivity precheck.
# One probe is too strict: the terminal is sometimes still coming up at 4:30pm,
# and on 2026-08-21 a merely-late terminal cost the site a full week of data.
$connected = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    Log "Checking Bloomberg Terminal connection (attempt $attempt of 3)..."
    python -c "from xbbg import blp; v = blp.bdp('AAPL US Equity', 'PX_LAST'); assert v is not None and len(v) > 0" 2>&1 |
        Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -eq 0) { $connected = $true; break }
    if ($attempt -lt 3) {
        Log "Not connected -- retrying in 5 minutes."
        Start-Sleep -Seconds 300
    }
}
if (-not $connected) {
    Log "Bloomberg Terminal not connected after 3 attempts -- skipping this week's run (no snapshot committed)."
    Send-HubReport 'awaiting_human' 'Bloomberg Terminal not connected - weekly snapshot skipped; needs a terminal login and a manual run'
    exit 0
}
Log "Bloomberg connected."

# 2) Earnings calendar + consensus estimates.
Log "Running pull_earnings.py ..."
python scripts\pull_earnings.py 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "pull_earnings.py FAILED (exit $LASTEXITCODE) -- aborting."; exit 1 }

# 3) Estimate histories (chains pull_prices.py internally).
Log "Running pull_estimates.py ..."
python scripts\pull_estimates.py 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { Log "pull_estimates.py FAILED (exit $LASTEXITCODE) -- aborting."; exit 1 }

# 4) Commit & push the new snapshots only.
$today = Get-Date -Format 'yyyy-MM-dd'
git add output/snapshots 2>&1 | Tee-Object -FilePath $log -Append
$staged = git diff --cached --name-only
if ([string]::IsNullOrWhiteSpace($staged)) {
    Log "No snapshot changes to commit (pulls produced no new files)."
} else {
    git commit -m "data: snapshot $today (earnings + estimates)" 2>&1 | Tee-Object -FilePath $log -Append
    git push 2>&1 | Tee-Object -FilePath $log -Append
    if ($LASTEXITCODE -ne 0) { Log "git push FAILED (exit $LASTEXITCODE)."; exit 1 }
    Log "Committed & pushed snapshot $today."
}

Log "=== Weekly BBG update complete ==="
exit 0
