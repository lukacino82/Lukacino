@echo off
rem Keeps run_live.py running across crashes and, via a "run at logon" Task
rem Scheduler entry (see the "Auto-start after a reboot" section in
rem ARCHITECTURE.md / sierra_chart/README.md), across a Windows reboot too.
rem
rem This is a supervisor loop, NOT a replacement for run_live.py's own
rem retry logic: run_live.py's while-loop already never exits on an
rem ordinary tick error (bad row, missing file, etc. -- see its
rem "except Exception" clause), so in practice this only ever restarts
rem run_live.py after something outside its control kills the whole
rem process (a stray Ctrl+C, the console window being closed, a machine
rem sleep/wake glitch, or -- the actual gap this exists to close -- the
rem machine rebooting).
rem
rem Deliberately does NOT run "git pull" automatically -- code updates stay
rem a manual, reviewed step exactly as before. Since each restart launches
rem a brand-new "python -m trading_system.run_live" process that re-reads
rem trading_system/ from disk, a manual "git pull" followed by one Ctrl+C
rem on the running window is enough to pick up a new build; the loop below
rem then relaunches it with the new code automatically.

setlocal

set REPO_DIR=C:\LukacinoGit
set BRIDGE_DIR=C:\SierraChart\TradingHypothesisBridge
set INSTRUMENT=NQ
set HISTORY_OUT=C:\SierraChart\TradingHypothesisBridge\NQ\historical_intraday.csv
set LOG_FILE=C:\SierraChart\TradingHypothesisBridge\NQ\run_live_supervisor.log

if not exist "C:\SierraChart\TradingHypothesisBridge\NQ" mkdir "C:\SierraChart\TradingHypothesisBridge\NQ"

:loop
echo [%date% %time%] Starting run_live.py >> "%LOG_FILE%"
cd /d "%REPO_DIR%"
python -m trading_system.run_live --bridge-dir "%BRIDGE_DIR%" --instrument %INSTRUMENT% --history-out "%HISTORY_OUT%" >> "%LOG_FILE%" 2>&1
echo [%date% %time%] run_live.py exited (code %ERRORLEVEL%) -- restarting in 10s >> "%LOG_FILE%"
timeout /t 10 /nobreak >nul
goto loop
