# Self-check the environment (ASCII only: see run.ps1 for the reason)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$libs = Join-Path $root 'libs'
$py   = 'D:\Anaconda3\envs\agent-rag\python.exe'

$envFile = Join-Path $here '.env'
if (Test-Path $envFile) {
    Get-Content -LiteralPath $envFile -Encoding utf8 | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

$env:PYTHONPATH = $libs
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $here
& $py check_env.py
