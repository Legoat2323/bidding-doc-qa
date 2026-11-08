# Launch the FastAPI service.
# Usage: powershell -ExecutionPolicy Bypass -File .\run_api.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$env:PYTHONPATH = Split-Path -Parent $here
$env:PYTHONIOENCODING = "utf-8"

$py = "D:\Anaconda3\envs\agent-rag\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

Write-Host "Starting API on http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
& $py -m uvicorn api.main:app --host 127.0.0.1 --port 8000
