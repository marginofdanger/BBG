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

# 1) Bloomberg connectivity precheck.
Log "Checking Bloomberg Terminal connection..."
python -c "from xbbg import blp; v = blp.bdp('AAPL US Equity', 'PX_LAST'); assert v is not None and len(v) > 0" 2>&1 |
    Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) {
    Log "Bloomberg Terminal not connected -- skipping this week's run (no snapshot committed)."
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
