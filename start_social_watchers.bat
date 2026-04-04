@echo off
REM Start All Gold Tier Social Media Watchers
REM =========================================
REM Starts Facebook, Instagram, X watchers and orchestrator

echo ============================================================
echo   Gold Tier Social Media Integration - Startup
echo ============================================================
echo.
echo Starting services...
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    pause
    exit /b 1
)

REM Check Playwright
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo Installing Playwright...
    pip install playwright
    playwright install chromium
)

REM Start Facebook Watcher
echo [1/5] Starting Facebook Watcher...
start "Facebook Watcher" cmd /k "python facebook_watcher.py"
timeout /t 3 /nobreak >nul

REM Start Instagram Watcher
echo [2/5] Starting Instagram Watcher...
start "Instagram Watcher" cmd /k "python instagram_watcher.py"
timeout /t 3 /nobreak >nul

REM Start X (Twitter) Watcher
echo [3/5] Starting X (Twitter) Watcher...
start "X Watcher" cmd /k "python x_watcher.py"
timeout /t 3 /nobreak >nul

REM Start Orchestrator
echo [4/5] Starting Orchestrator...
start "Orchestrator" cmd /k "python orchestrator.py"
timeout /t 3 /nobreak >nul

REM Start Summary Generator (hourly)
echo [5/5] Summary generator will run on demand
echo.
echo ============================================================
echo   All services started!
echo ============================================================
echo.
echo Running services:
echo   - Facebook Watcher (monitoring messages/notifications)
echo   - Instagram Watcher (monitoring DMs/notifications)
echo   - X (Twitter) Watcher (monitoring mentions/DMs)
echo   - Orchestrator (processing tasks)
echo.
echo To generate summaries:
echo   python social_summary.py --all
echo.
echo To post to social media:
echo   python social_poster.py --platform facebook --text "Your post"
echo   python social_poster.py --platform x --text "Tweet content"
echo.
echo To stop all services: Close the command windows or press Ctrl+C
echo ============================================================
echo.
pause
