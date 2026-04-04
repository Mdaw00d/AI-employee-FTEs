#!/usr/bin/env python3
"""
Odoo Community 19 Local Setup Script for Windows
================================================
Installs and configures Odoo 19 Community Edition for local development.

Requirements:
- Python 3.8+ installed
- PostgreSQL 14+ installed (or will prompt for installation)
- Administrator privileges for some operations

Usage:
    python odoo_setup.py

Post-Installation:
    - Odoo runs at http://localhost:8069
    - Default admin password: admin (CHANGE IMMEDIATELY)
    - Database: odoo_db
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import subprocess
import json
import hashlib
import getpass
from pathlib import Path
from datetime import datetime

# Configuration
ODOO_VERSION = "19.0"
ODOO_DOWNLOAD_URL = "https://github.com/odoo/odoo/archive/refs/heads/master.zip"
INSTALL_DIR = Path(r"C:\Odoo19")
DATA_DIR = INSTALL_DIR / "odoo_data"
DB_NAME = "odoo_db"
DB_USER = "odoo_user"
DB_PASSWORD = "odoo_secure_pass_2026"  # CHANGE IN PRODUCTION
ADMIN_PASSWORD = "admin"  # CHANGE IMMEDIATELY AFTER FIRST LOGIN
ODOO_PORT = 8069

# Scoop PostgreSQL path (user installation)
SCOOP_PG_PATH = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin")
if SCOOP_PG_PATH.exists():
    os.environ["PATH"] = str(SCOOP_PG_PATH) + os.pathsep + os.environ.get("PATH", "")

# Platinum Tier: Enable HTTPS with self-signed cert
ENABLE_HTTPS = False  # Set to True for production
HTTPS_CERT_PATH = INSTALL_DIR / "ssl" / "odoo.crt"
HTTPS_KEY_PATH = INSTALL_DIR / "ssl" / "odoo.key"

# Platinum Tier: Backup configuration
BACKUP_ENABLED = True
BACKUP_DIR = INSTALL_DIR / "backups"
BACKUP_SCHEDULE = "0 2 * * *"  # Daily at 2 AM (cron format)


def print_header(text):
    """Print formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_step(step_num, text):
    """Print step indicator."""
    print(f"\n[Step {step_num}] {text}")
    print("-" * 40)


def run_command(cmd, capture=False, shell=True):
    """Execute shell command with error handling."""
    try:
        if capture:
            result = subprocess.run(
                cmd,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, shell=shell, timeout=300)
            return result.returncode == 0, "", ""
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_python():
    """Verify Python installation and version."""
    print_step(1, "Checking Python Installation")
    
    version = sys.version_info
    print(f"Python Version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ required. Please upgrade.")
        return False
    
    print("✅ Python version OK")
    return True


def check_postgresql():
    """Check if PostgreSQL is installed and running."""
    print_step(2, "Checking PostgreSQL Installation")
    
    # Check if psql is available
    success, stdout, stderr = run_command("pg_config --version", capture=True)
    
    if not success:
        print("⚠️  PostgreSQL not found in PATH")
        print("\n📦 Install PostgreSQL:")
        print("   1. Download from: https://www.postgresql.org/download/windows/")
        print("   2. Run installer, keep default settings")
        print("   3. Add PostgreSQL bin to PATH (e.g., C:\\Program Files\\PostgreSQL\\16\\bin)")
        print("\n   Or via winget (admin terminal):")
        print("   > winget install PostgreSQL.PostgreSQL")
        print("\nRun this script again after installation.")
        return False
    
    print(f"PostgreSQL: {stdout.strip()}")
    
    # Check if server is running by trying to connect
    success, stdout, stderr = run_command('psql -U postgres -c "SELECT 1;"', capture=True)
    if success:
        print("✅ PostgreSQL is running")
        return True
    
    # Try Scoop PostgreSQL path
    scoop_pg_data = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\data")
    if scoop_pg_data.exists():
        print("📦 Found Scoop PostgreSQL installation")
        print("   Starting PostgreSQL server...")
        success, stdout, stderr = run_command(
            f'pg_ctl start -D "{scoop_pg_data}" -l "{scoop_pg_data}\\logfile.log"',
            capture=True
        )
        if success or "server starting" in stdout.lower() or "already started" in stdout.lower():
            print("✅ PostgreSQL started successfully")
            return True
    
    # Check Windows service
    success, stdout, stderr = run_command('sc query postgresql* | find "RUNNING"', capture=True)
    if success:
        print("✅ PostgreSQL is running")
        return True
    
    print("⚠️  PostgreSQL service not running")
    print("\n   Start PostgreSQL manually:")
    print("   > pg_ctl start -D \"C:\\Program Files\\PostgreSQL\\16\\data\"")
    print("   (Adjust path for your installation)")
    return False


def setup_database():
    """Create Odoo database and user."""
    print_step(3, "Setting Up Database")
    
    # Use postgres superuser for initial setup
    print("Using PostgreSQL superuser 'postgres' for setup...")
    print("(You may be prompted for password)")
    
    # Create database user
    create_user_sql = f"""
    DO $$
    BEGIN
       IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{DB_USER}') THEN
          CREATE ROLE {DB_USER} WITH LOGIN PASSWORD '{DB_PASSWORD}';
       END IF;
    END
    $$;
    """
    
    success, stdout, stderr = run_command(
        f'psql -U postgres -c "{create_user_sql}"',
        capture=True
    )
    
    if not success and "password" in stderr.lower():
        # Try with password prompt
        print("\nEntering PostgreSQL password mode...")
        success, stdout, stderr = run_command(
            f'psql -U postgres -c "CREATE ROLE {DB_USER} WITH LOGIN PASSWORD \'{DB_PASSWORD}\';"',
            capture=True
        )
    
    if success or "already exists" in stderr.lower():
        print(f"✅ Database user '{DB_USER}' created/exists")
    else:
        print(f"⚠️  Could not create user: {stderr}")
        print("   You may need to create user manually in pgAdmin")
    
    # Create database
    success, stdout, stderr = run_command(
        f'psql -U postgres -c "CREATE DATABASE {DB_NAME} OWNER {DB_USER};"',
        capture=True
    )
    
    if success:
        print(f"✅ Database '{DB_NAME}' created")
    elif "already exists" in stderr.lower():
        print(f"✅ Database '{DB_NAME}' already exists")
    else:
        print(f"⚠️  Could not create database: {stderr}")
        print("   You may need to create database manually")
    
    # Grant privileges
    run_command(
        f'psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};"',
        capture=True
    )
    
    return True


def download_odoo():
    """Download Odoo Community source code."""
    print_step(4, "Downloading Odoo Community")
    
    if INSTALL_DIR.exists():
        print(f"✅ Odoo directory already exists: {INSTALL_DIR}")
        print("   Skipping download. Delete directory to re-download.")
        return True
    
    print(f"Download URL: {ODOO_DOWNLOAD_URL}")
    print(f"Install Directory: {INSTALL_DIR}")
    print("\n⏳ Downloading Odoo (this may take 2-5 minutes)...")
    
    # Create install directory
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download using PowerShell (more reliable on Windows)
    download_script = f"""
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "{ODOO_DOWNLOAD_URL}" -OutFile "{INSTALL_DIR}\\odoo.zip"
    Expand-Archive -Path "{INSTALL_DIR}\\odoo.zip" -DestinationPath "{INSTALL_DIR}" -Force
    Remove-Item "{INSTALL_DIR}\\odoo.zip"
    """
    
    success, stdout, stderr = run_command(
        f'powershell -Command "{download_script}"',
        capture=True
    )
    
    if not success:
        print(f"⚠️  Download failed: {stderr}")
        print("\n📥 Manual Download:")
        print(f"   1. Visit: {ODOO_DOWNLOAD_URL}")
        print(f"   2. Download and extract to: {INSTALL_DIR}")
        print("   3. Rename extracted folder to remove version suffix")
        return False
    
    print("✅ Odoo downloaded and extracted")
    
    # Find the extracted directory (may have version suffix)
    extracted_dirs = [d for d in INSTALL_DIR.iterdir() if d.is_dir() and 'odoo' in d.name.lower()]
    if extracted_dirs:
        print(f"   Extracted to: {extracted_dirs[0]}")
    
    return True


def install_dependencies():
    """Install Python dependencies for Odoo."""
    print_step(5, "Installing Python Dependencies")
    
    # Find requirements.txt in Odoo directory
    odoo_dir = None
    for d in INSTALL_DIR.iterdir():
        if d.is_dir() and 'odoo' in d.name.lower():
            odoo_dir = d
            break
    
    if not odoo_dir:
        odoo_dir = INSTALL_DIR
    
    requirements_file = odoo_dir / "requirements.txt"
    
    if not requirements_file.exists():
        print(f"⚠️  requirements.txt not found at {requirements_file}")
        print("   Creating minimal requirements...")
        
        # Create minimal requirements for basic Odoo functionality
        minimal_requirements = """
werkzeug>=2.0
lxml>=4.6
psycopg2-binary>=2.9
Pillow>=8.0
requests>=2.25
urllib3>=1.26
chardet>=4.0
polib>=1.1
decorator>=5.0
docutils>=0.15
gevent>=21.0
greenlet>=1.0
idna>=2.10
Jinja2>=3.0
MarkupSafe>=2.0
num2words>=0.5
pyopenssl>=20.0
PyPDF2>=1.26
python-dateutil>=2.8
pytz>=2021
reportlab>=3.5
six>=1.15
suds-community>=0.6
qrcode>=6.1
openpyxl>=3.0
xlwt>=1.3
xlrd>=2.0
xlsxwriter>=1.4
"""
        requirements_file.write_text(minimal_requirements.strip())
    
    print(f"Installing from: {requirements_file}")
    print("⏳ This may take 3-10 minutes...")
    
    success, stdout, stderr = run_command(
        f'pip install -r "{requirements_file}"',
        capture=True
    )
    
    if success:
        print("✅ Dependencies installed")
    else:
        print(f"⚠️  Some dependencies may have failed: {stderr[:200]}")
        print("   You can install missing packages manually:")
        print("   > pip install psycopg2-binary werkzeug lxml Pillow")
    
    return True


def create_odoo_config():
    """Create Odoo configuration file."""
    print_step(6, "Creating Odoo Configuration")
    
    config_dir = DATA_DIR / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = config_dir / "odoo.conf"
    
    # Find Odoo source directory
    odoo_dir = None
    for d in INSTALL_DIR.iterdir():
        if d.is_dir() and 'odoo' in d.name.lower():
            odoo_dir = d
            break
    
    if not odoo_dir:
        odoo_dir = INSTALL_DIR
    
    addons_path = odoo_dir / "addons"
    if not addons_path.exists():
        addons_path = odoo_dir
    
    config_content = f"""
[options]
# Server Configuration
http_port = {ODOO_PORT}
workers = 2
max_cron_threads = 1

# Database Configuration
db_host = localhost
db_port = 5432
db_name = {DB_NAME}
db_user = {DB_USER}
db_password = {DB_PASSWORD}

# Admin Password (for database management)
admin_passwd = {ADMIN_PASSWORD}

# File Storage
data_dir = {DATA_DIR}
filestore_dir = {DATA_DIR / "filestore"}

# Addons Path
addons_path = {addons_path}

# Logging
logfile = {DATA_DIR / "logs" / "odoo.log"}
log_level = info

# Security
# list_db = False  # Disable database listing in production

# Platinum Tier: HTTPS Configuration
"""
    
    if ENABLE_HTTPS:
        config_content += f"""
# SSL/HTTPS (Platinum Tier)
ssl_certificate = {HTTPS_CERT_PATH}
ssl_private_key = {HTTPS_KEY_PATH}
"""
    else:
        config_content += "\n# HTTPS disabled for development\n"
    
    config_file.write_text(config_content)
    print(f"✅ Configuration created: {config_file}")
    
    # Create necessary directories
    (DATA_DIR / "filestore").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    
    if ENABLE_HTTPS:
        create_ssl_certificates()
    
    return True


def create_ssl_certificates():
    """Generate self-signed SSL certificates (Platinum Tier)."""
    print_step(6.5, "Generating SSL Certificates (Platinum Tier)")
    
    ssl_dir = HTTPS_CERT_PATH.parent
    ssl_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate private key and certificate using OpenSSL
    print("Generating self-signed certificate...")
    
    success, stdout, stderr = run_command(
        f'openssl req -x509 -newkey rsa:2048 -keyout "{HTTPS_KEY_PATH}" '
        f'-out "{HTTPS_CERT_PATH}" -days 365 -nodes '
        f'-subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"',
        capture=True
    )
    
    if success:
        print(f"✅ SSL Certificate: {HTTPS_CERT_PATH}")
        print(f"✅ SSL Private Key: {HTTPS_KEY_PATH}")
        print("\n⚠️  Browsers will show security warning for self-signed cert")
        print("   Accept the warning to proceed, or use a CA-signed cert for production")
    else:
        print(f"⚠️  SSL generation failed: {stderr}")
        print("   Install OpenSSL from: https://slproweb.com/products/Win32OpenSSL.html")
        print("   Or disable HTTPS in config (ENABLE_HTTPS = False)")


def setup_backup_system():
    """Configure automated backups (Platinum Tier)."""
    print_step(6.7, "Setting Up Backup System (Platinum Tier)")
    
    if not BACKUP_ENABLED:
        print("⏭️  Backups disabled in configuration")
        return True
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create backup script
    backup_script = DATA_DIR / "scripts" / "backup.bat"
    backup_script.parent.mkdir(parents=True, exist_ok=True)
    
    backup_content = f"""@echo off
REM Odoo Database Backup Script
REM Runs daily via Task Scheduler

set PGUSER=postgres
set PGPASSWORD={DB_PASSWORD}
set BACKUP_DIR={BACKUP_DIR}
set DB_NAME={DB_NAME}
set TIMESTAMP=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%

echo Starting backup at %TIMESTAMP%

REM Create backup directory for today
mkdir "%BACKUP_DIR%\\%date:~-4%%date:~3,2%%date:~0,2%"

REM Dump database
pg_dump -h localhost -U %PGUSER% %DB_NAME% > "%BACKUP_DIR%\\%date:~-4%%date:~3,2%%date:~0,2%\\%DB_NAME%_%TIMESTAMP%.sql"

REM Backup filestore
xcopy /E /I /Y "{DATA_DIR}\\filestore" "%BACKUP_DIR%\\%date:~-4%%date:~3,2%%date:~0,2%\\filestore"

REM Keep only last 30 days
forfiles /p "%BACKUP_DIR%" /s /m *.* /d -30 /c "cmd /c del @path"

echo Backup completed
"""
    
    backup_script.write_text(backup_content)
    print(f"✅ Backup script: {backup_script}")
    
    # Create scheduled task
    print("\n📅 To schedule daily backups, run as Administrator:")
    print(f'   schtasks /Create /TN "Odoo Backup" /TR "{backup_script}" /SC DAILY /ST 02:00 /RU SYSTEM')
    
    return True


def create_start_script():
    """Create script to start Odoo server."""
    print_step(6.9, "Creating Start Script")
    
    start_script = INSTALL_DIR / "start_odoo.bat"
    
    # Find Odoo source directory
    odoo_dir = None
    for d in INSTALL_DIR.iterdir():
        if d.is_dir() and 'odoo' in d.name.lower():
            odoo_dir = d
            break
    
    if not odoo_dir:
        odoo_dir = INSTALL_DIR
    
    odoo_bin = odoo_dir / "odoo-bin"
    if not odoo_bin.exists():
        odoo_bin = odoo_dir / "odoo.py"
    
    config_file = DATA_DIR / "config" / "odoo.conf"
    
    start_content = f"""@echo off
REM Odoo 19 Startup Script
REM Starts Odoo server on http://localhost:{ODOO_PORT}

echo Starting Odoo 19 Community...
echo Configuration: {config_file}
echo

cd /d "{odoo_dir}"
python "{odoo_bin}" -c "{config_file}"

pause
"""
    
    start_script.write_text(start_content)
    print(f"✅ Start script: {start_script}")
    
    # Create stop script
    stop_script = INSTALL_DIR / "stop_odoo.bat"
    stop_content = f"""@echo off
REM Stop Odoo Server
echo Stopping Odoo...
taskkill /F /FI "WINDOWTITLE eq Odoo*" /T 2>nul
echo Done.
"""
    stop_script.write_text(stop_content)
    
    return True


def initialize_odoo():
    """Initialize Odoo database with admin user."""
    print_step(7, "Initializing Odoo Database")
    
    print("\n⏳ Starting Odoo for first-time initialization...")
    print("   This will create database tables (2-5 minutes)")
    print("   Odoo will start, then you can stop it with Ctrl+C")
    print("\n   Press Enter to continue...")
    input()
    
    # Find Odoo executable
    odoo_dir = None
    for d in INSTALL_DIR.iterdir():
        if d.is_dir() and 'odoo' in d.name.lower():
            odoo_dir = d
            break
    
    if not odoo_dir:
        odoo_dir = INSTALL_DIR
    
    odoo_bin = odoo_dir / "odoo-bin"
    if not odoo_bin.exists():
        odoo_bin = odoo_dir / "odoo.py"
    
    config_file = DATA_DIR / "config" / "odoo.conf"
    
    print(f"\n🚀 Starting Odoo initialization...")
    print(f"   Access at: http://localhost:{ODOO_PORT}")
    print(f"   Admin password: {ADMIN_PASSWORD}")
    print("\n   ⚠️  CHANGE ADMIN PASSWORD after first login!")
    print("\n   Press Ctrl+C after you see 'Odoo is running' message")
    print("-" * 60)
    
    # Start Odoo (this will run until user stops it)
    subprocess.run(
        f'python "{odoo_bin}" -c "{config_file}"',
        shell=True
    )
    
    return True


def print_summary():
    """Print installation summary and next steps."""
    print_header("Installation Complete!")
    
    print(f"""
✅ Odoo 19 Community installed at: {INSTALL_DIR}
✅ Database: {DB_NAME} (PostgreSQL)
✅ Web Interface: http://localhost:{ODOO_PORT}
✅ Configuration: {DATA_DIR / "config" / "odoo.conf"}

📁 Quick Commands:
   Start: {INSTALL_DIR}\\start_odoo.bat
   Stop:  {INSTALL_DIR}\\stop_odoo.bat

🔐 Security:
   - Default admin password: {ADMIN_PASSWORD}
   - ⚠️  CHANGE THIS IMMEDIATELY after first login!
   - Go to: http://localhost:{ODOO_PORT}/web/database/manager

📊 Platinum Tier Features:
   - HTTPS: {'Enabled' if ENABLE_HTTPS else 'Disabled (set ENABLE_HTTPS=True)'}
   - Backups: {'Enabled' if BACKUP_ENABLED else 'Disabled (set BACKUP_ENABLED=True)'}
   - Backup Dir: {BACKUP_DIR}

🔗 Integration with MCP Server:
   - Run: python odoo_mcp.py
   - MCP provides JSON-RPC API for accounting operations
   - See odoo_mcp.py for API documentation

📚 Next Steps:
   1. Start Odoo: {INSTALL_DIR}\\start_odoo.bat
   2. Open browser: http://localhost:{ODOO_PORT}
   3. Create your first database
   4. Install Accounting module
   5. Configure chart of accounts
   6. Run MCP server for API access

🎉 Happy Odoo-ing!
""")


def main():
    """Main installation routine."""
    print_header("Odoo 19 Community Local Setup for Windows")
    
    print(f"Version: {ODOO_VERSION}")
    print(f"Install Dir: {INSTALL_DIR}")
    print(f"Database: {DB_NAME}")
    print(f"Port: {ODOO_PORT}")
    
    # Check prerequisites
    if not check_python():
        sys.exit(1)
    
    if not check_postgresql():
        sys.exit(1)
    
    # Setup
    setup_database()
    download_odoo()
    install_dependencies()
    create_odoo_config()
    setup_backup_system()
    create_start_script()
    
    print_header("Ready to Initialize")
    print("""
The installation is complete. You can now:

1. Initialize Odoo database (recommended for first-time setup)
2. Skip initialization and start Odoo manually later

""")
    
    # Non-interactive mode: skip initialization
    print("Skipping interactive initialization (non-interactive mode)")
    print("To initialize, run: start_odoo.bat")
    
    # choice = input("Initialize Odoo database now? (y/n): ").strip().lower()
    # if choice == 'y':
    #     initialize_odoo()
    
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nCheck the error message above and try again.")
        sys.exit(1)
