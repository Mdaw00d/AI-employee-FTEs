@echo off
REM ===================================================================
REM Complete Odoo 19 + MCP Server Setup
REM ===================================================================
REM This script:
REM   1. Extracts Odoo source code
REM   2. Installs Python dependencies
REM   3. Starts Odoo server
REM   4. Starts MCP server
REM ===================================================================

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║       Complete Odoo 19 + MCP Server Setup                ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Set PostgreSQL path
set "PGPATH=C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin"
set "PATH=%PGPATH%;%PATH%"

REM Check if PostgreSQL is running
echo [1/5] Checking PostgreSQL...
psql -U postgres -c "SELECT 1;" >nul 2>&1
if errorlevel 1 (
    echo PostgreSQL not running. Starting...
    pg_ctl start -D "C:\Users\LAPTER.PK\scoop\apps\postgresql\current\data" -l "C:\Users\LAPTER.PK\scoop\apps\postgresql\current\data\logfile.log"
) else (
    echo PostgreSQL is running.
)
echo.

REM Extract Odoo if needed
echo [2/5] Checking Odoo source code...
if exist "C:\Odoo19\odoo-master\odoo-bin" (
    echo Odoo source already extracted.
) else if exist "C:\Odoo19\odoo.zip" (
    echo Extracting Odoo source code...
    powershell -Command "Expand-Archive -Path 'C:\Odoo19\odoo.zip' -DestinationPath 'C:\Odoo19' -Force"
    echo Cleaning up...
    del "C:\Odoo19\odoo.zip"
) else (
    echo Downloading Odoo source code...
    powershell -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/odoo/odoo/archive/refs/heads/master.zip' -OutFile 'C:\Odoo19\odoo.zip' -UseBasicParsing"
    echo Extracting...
    powershell -Command "Expand-Archive -Path 'C:\Odoo19\odoo.zip' -DestinationPath 'C:\Odoo19' -Force"
    del "C:\Odoo19\odoo.zip"
)

REM Find Odoo directory
for /d %%i in ("C:\Odoo19\odoo-*") do set ODOODIR=%%i
if not defined ODOODIR (
    for /d %%i in ("C:\Odoo19\odoo-master") do set ODOODIR=%%i
)
if not defined ODOODIR (
    echo ERROR: Could not find Odoo directory
    pause
    exit /b 1
)
echo Odoo directory: %ODOODIR%
echo.

REM Install dependencies
echo [3/5] Installing Python dependencies...
if exist "%ODOODIR%\requirements.txt" (
    echo Installing from %ODOODIR%\requirements.txt
    pip install -r "%ODOODIR%\requirements.txt"
) else (
    echo Installing minimal requirements...
    pip install werkzeug lxml psycopg2-binary Pillow requests urllib3 chardet decorator docutils gevent greenlet idna Jinja2 MarkupSafe num2words pyopenssl PyPDF2 python-dateutil pytz reportlab six qrcode openpyxl xlwt xlrd xlsxwriter
)
echo.

REM Update odoo_mcp.py with correct Odoo directory
echo [4/5] Updating configuration...
set "SCRIPTDIR=%~dp0"

REM Start Odoo server
echo [5/5] Starting Odoo server...
echo.
echo ═══════════════════════════════════════════════════════════
echo Odoo will start on http://localhost:8069
echo Press Ctrl+C to stop Odoo (will also stop MCP server)
echo ═══════════════════════════════════════════════════════════
echo.

cd /d "%ODOODIR%"
start "" cmd /k "echo Starting Odoo... && python odoo-bin -c '%SCRIPTDIR%..\Odoo19\odoo_data\config\odoo.conf'"

echo.
echo Waiting 20 seconds for Odoo to start...
timeout /t 20 /nobreak >nul

echo.
echo Starting MCP Server...
cd /d "%SCRIPTDIR%"
python odoo_mcp.py

pause
