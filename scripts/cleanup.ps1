# Cleanup script for project-bot-easy-apply
# Run from project root in PowerShell: .\scripts\cleanup.ps1

Write-Host "Running cleanup: will remove cached token, CSV exports, and Python caches..."

$errors = @()

# Remove cached API token
$tokenPath = Join-Path $PWD "data\.api_token.json"
if (Test-Path $tokenPath) {
    try {
        Remove-Item $tokenPath -Force
        Write-Host "Removed: $tokenPath"
    } catch {
        $errors += "Failed to remove $tokenPath"
        $errors += $_.Exception.Message
    }
} else {
    Write-Host "Not found: $tokenPath"
}

# Remove generated CSV exports
$csvPath = Join-Path $PWD "data\exports\extractor_job_links.csv"
if (Test-Path $csvPath) {
    try {
        Remove-Item $csvPath -Force
        Write-Host "Removed: $csvPath"
    } catch {
        $errors += "Failed to remove $csvPath"
        $errors += $_.Exception.Message
    }
} else {
    Write-Host "Not found: $csvPath"
}

# Remove top-level __pycache__ and any .pyc files under project (excluding venv)
Get-ChildItem -Path $PWD -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { ($_.Name -eq '__pycache__' -and -not ($_.FullName -match "\\venv\\")) -or ($_.Extension -eq '.pyc' -and -not ($_.FullName -match "\\venv\\")) } |
    ForEach-Object {
        try {
            if ($_.PSIsContainer) {
                Remove-Item $_.FullName -Recurse -Force -ErrorAction Stop
                Write-Host "Removed directory: $($_.FullName)"
            } else {
                Remove-Item $_.FullName -Force -ErrorAction Stop
                Write-Host "Removed file: $($_.FullName)"
            }
        } catch {
            $errors += "Failed to remove $($_.FullName)"
            $errors += $_.Exception.Message
        }
    }

if ($errors.Count -gt 0) {
    Write-Host "Encountered errors:" -ForegroundColor Yellow
    $errors | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "Cleanup completed successfully." -ForegroundColor Green
}
