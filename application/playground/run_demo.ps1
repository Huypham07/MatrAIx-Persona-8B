# Start Playground - Windows PowerShell

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $HERE

$REPO_ROOT = (Resolve-Path (Join-Path $HERE "..\..")).Path
$PLAYGROUND_CORE_DIR = Join-Path $REPO_ROOT "packages\playground\src"

Write-Host "[run_demo] Repo root: $REPO_ROOT"

# ------------------------------------------------------------
# Load .env.local
# ------------------------------------------------------------

$envLocal = Join-Path $HERE ".env.local"

if (Test-Path $envLocal) {
    Write-Host "[run_demo] Loading .env.local"

    Get-Content $envLocal | ForEach-Object {
        $line = $_.Trim()

        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)

            if ($parts.Count -eq 2) {
                $key = $parts[0].Trim()
                $value = $parts[1].Trim()

                if ($value.Length -ge 2) {
                    if (
                        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                        ($value.StartsWith("'") -and $value.EndsWith("'"))
                    ) {
                        $value = $value.Substring(1, $value.Length - 2)
                    }
                }

                Set-Item "Env:$key" $value
            }
        }
    }
}

# ------------------------------------------------------------
# Find Python
# ------------------------------------------------------------

if ($env:VENV) {
    $venvPath = $env:VENV

    if (-not [System.IO.Path]::IsPathRooted($venvPath)) {
        $venvPath = Join-Path $REPO_ROOT $venvPath
    }

    $PY = Join-Path $venvPath "Scripts\python.exe"

    if (-not (Test-Path $PY)) {
        Write-Host "[run_demo] ERROR: Python not found:"
        Write-Host "           $PY"
        exit 1
    }
}
elseif ($env:VIRTUAL_ENV) {
    $PY = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
}
else {
    $PY = "python"
}

Write-Host "[run_demo] Python: $PY"

# ------------------------------------------------------------
# Host / Port
# ------------------------------------------------------------

if ($env:HOST) {
    $serverHost = $env:HOST
}
else {
    $serverHost = "127.0.0.1"
}

if ($env:PORT) {
    $serverPort = $env:PORT
}
else {
    $serverPort = "8765"
}

# ------------------------------------------------------------
# PYTHONPATH
# ------------------------------------------------------------

$pythonPaths = @(
    $REPO_ROOT
    (Join-Path $REPO_ROOT "src")
    (Join-Path $REPO_ROOT "environment\runtime")
    (Join-Path $REPO_ROOT "environment\agents")
    $PLAYGROUND_CORE_DIR
    $HERE
)

if ($env:PYTHONPATH) {
    $pythonPaths += $env:PYTHONPATH
}

$env:PYTHONPATH = $pythonPaths -join [System.IO.Path]::PathSeparator

if (-not $env:TOKENIZERS_PARALLELISM) {
    $env:TOKENIZERS_PARALLELISM = "false"
}

# ------------------------------------------------------------
# Check frontend
# ------------------------------------------------------------

$frontendDist = Join-Path $HERE "frontend\dist"

if (-not (Test-Path $frontendDist)) {
    Write-Host ""
    Write-Host "[run_demo] ERROR: frontend/dist not found."
    Write-Host ""
    Write-Host "Build the frontend first:"
    Write-Host ""
    Write-Host "  cd frontend"
    Write-Host "  npm install"
    Write-Host "  npm run build"
    Write-Host ""

    exit 1
}

# ------------------------------------------------------------
# Start server
# ------------------------------------------------------------

Write-Host ""
Write-Host "[run_demo] Serving on http://${serverHost}:${serverPort}"
Write-Host "[run_demo] Press Ctrl-C to stop"
Write-Host ""

& $PY -m uvicorn backend.api.app:app --host $serverHost --port $serverPort