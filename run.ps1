# Start the Document QA app (ASCII only on purpose:
# Windows PowerShell 5.1 reads BOM-less .ps1 as ANSI, which corrupts Chinese text)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$libs = Join-Path $root 'libs'
$py   = 'D:\Anaconda3\envs\agent-rag\python.exe'

# ---- load .env ----
$envFile = Join-Path $here '.env'
if (Test-Path $envFile) {
    Get-Content -LiteralPath $envFile -Encoding utf8 | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

if (-not $env:DASHSCOPE_API_KEY -or $env:DASHSCOPE_API_KEY.Length -lt 20) {
    Write-Host "==============================================" -ForegroundColor Red
    Write-Host " DASHSCOPE_API_KEY is missing or too short" -ForegroundColor Red
    Write-Host " Edit this file and put your key on line 1:" -ForegroundColor Yellow
    Write-Host "   $envFile" -ForegroundColor Yellow
    Write-Host "==============================================" -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = $libs
$env:GRADIO_ANALYTICS_ENABLED = 'False'
$env:PYTHONIOENCODING = 'utf-8'
# Localhost must bypass any system proxy, otherwise gradio launch fails with
# "When localhost is not accessible, a shareable link must be created."
$env:NO_PROXY = '127.0.0.1,localhost'
$env:no_proxy = '127.0.0.1,localhost'

Write-Host "python   : $py"
Write-Host "libs     : $libs"
Write-Host "api key  : $($env:DASHSCOPE_API_KEY.Substring(0,8))..."
Write-Host ""

Set-Location $here
& $py main.py
