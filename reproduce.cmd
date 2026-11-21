@echo off
REM Reproduce the frozen baseline in README.md ("score table" section), end to end.
REM
REM Why: README's score table is the official scorecard. This script is
REM the ONLY accepted way to (re)produce those numbers. When a metric changes,
REM run this first to tell "the code changed" apart from "the world
REM changed" (model update, API drift, network).
REM
REM Prerequisites (same as run_exp.cmd): the project runs on
REM   D:\Anaconda3\envs\agent-rag\python.exe + vendored libs in courses\libs
REM pip install is NOT part of this script because this machine's sandbox
REM blocks it. On a fresh machine: pip install -r requirements-lock.txt
REM before running this.
REM
REM Steps:
REM   1. unit tests     run_tests.py   (offline)
REM   2. dev-set eval   bid_eval.py    (online, needs .env API key)
REM   3. holdout        holdout.py     (online, JUDGE BY HAND -> holdout_report.md)
REM   4. latency        latency.py     (online)
REM
REM Usage: reproduce.cmd

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

echo === 1/4 unit tests (offline) ===
"%PY%" "%HERE%run_tests.py" || exit /b 1

echo === 2/4 dev-set eval (online) ===
"%PY%" "%HERE%bid_eval.py" || exit /b 1

echo === 3/4 holdout (online, judge by hand) ===
"%PY%" "%HERE%holdout.py" || exit /b 1

echo === 4/4 latency (online) ===
"%PY%" "%HERE%latency.py" || exit /b 1

echo.
echo Done. Compare every number against README.md (the score table).
echo Holdout answers land in holdout_report.md and must be judged by hand.
