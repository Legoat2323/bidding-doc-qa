@echo off
REM Run an experiment with the project interpreter.
REM
REM Why: .venv in this project is empty (only pip). The project actually runs on
REM D:\Anaconda3\envs\agent-rag + vendored libs in courses\libs (PYTHONPATH).
REM A .cmd file is used instead of .ps1 because PowerShell script execution is blocked here.
REM
REM Usage:
REM   run_exp.cmd                                  (default: experiments\exp_threshold.py)
REM   run_exp.cmd experiments\exp_threshold.py 0.2 0.3 0.4
REM   run_exp.cmd bid_eval.py

setlocal
set "HERE=%~dp0"
set "PYTHONPATH=%HERE%..\libs"
set "PYTHONIOENCODING=utf-8"
set "ANONYMIZED_TELEMETRY=False"
set "PY=D:\Anaconda3\envs\agent-rag\python.exe"

if not exist "%PY%" (
  echo python not found: %PY%
  exit /b 1
)

if "%~1"=="" (
  "%PY%" "%HERE%experiments\exp_threshold.py"
) else (
  "%PY%" "%HERE%%~1" %2 %3 %4 %5 %6 %7 %8 %9
)
