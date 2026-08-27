$ErrorActionPreference = "Stop"

$ROOT = $PSScriptRoot
if (-not $ROOT) {
    $ROOT = (Get-Location).Path
}

# 1. Bat che do UTF-8 cho Python tren Windows
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# 2. Tu dong nap cau hinh tu .env.local (hoac .env)
$envLocal = Join-Path $ROOT "application\playground\.env.local"
if (-not (Test-Path $envLocal)) {
    $envLocal = Join-Path $ROOT "application\playground\.env"
}

if (Test-Path $envLocal) {
    Write-Host "[start_backend] Loading config from $envLocal" -ForegroundColor Cyan
    Get-Content $envLocal | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim().Trim('"').Trim("'")
                Set-Item "Env:$key" $val
            }
        }
    }
}

# 3. Cau hinh PYTHONPATH cho Monorepo
$paths = @(
    $ROOT
    (Join-Path $ROOT "src")
    (Join-Path $ROOT "environment\runtime")
    (Join-Path $ROOT "environment\agents")
    (Join-Path $ROOT "packages\playground\src")
    (Join-Path $ROOT "application\playground")
)
$env:PYTHONPATH = $paths -join [System.IO.Path]::PathSeparator

Write-Host "[start_backend] Starting MatrAIx Backend on http://127.0.0.1:8765 ..." -ForegroundColor Green
Write-Host "[start_backend] Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# 4. Khoi chay Uvicorn server
Set-Location (Join-Path $ROOT "application\playground")
uv run uvicorn backend.api.app:app --host 127.0.0.1 --port 8765