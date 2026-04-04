#!/usr/bin/env python3
"""
Odoo Complete Startup Script
============================
Starts Odoo server and MCP server automatically.

Usage:
    python start_all.py
"""

import os
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import subprocess
import time
import threading
from pathlib import Path

# Configuration
ODOO_INSTALL_DIR = Path(r"C:\Odoo19")
PG_PATH = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin")
SCRIPT_DIR = Path(__file__).parent

# Add PostgreSQL to PATH
if PG_PATH.exists():
    os.environ["PATH"] = str(PG_PATH) + os.pathsep + os.environ.get("PATH", "")

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def check_postgresql():
    """Ensure PostgreSQL is running."""
    print("[1/5] Checking PostgreSQL...")
    
    result = subprocess.run(
        'psql -U postgres -c "SELECT 1;"',
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print("   Starting PostgreSQL...")
        subprocess.run(
            f'pg_ctl start -D "{PG_PATH.parent}\\postgresql\\current\\data" -l "{PG_PATH.parent}\\postgresql\\current\\data\\logfile.log"',
            shell=True
        )
        time.sleep(2)
    
    print("   ✓ PostgreSQL running")
    return True


def find_odoo_dir():
    """Find Odoo source directory."""
    print("[2/5] Finding Odoo source...")
    
    for item in ODOO_INSTALL_DIR.iterdir():
        if item.is_dir() and 'odoo' in item.name.lower():
            print(f"   Found: {item}")
            return item
    
    return None


def extract_odoo_if_needed():
    """Extract Odoo from zip if not already extracted."""
    print("[2/5] Checking Odoo source...")
    
    odoo_dir = find_odoo_dir()
    if odoo_dir:
        return odoo_dir
    
    zip_file = ODOO_INSTALL_DIR / "odoo.zip"
    
    if not zip_file.exists():
        print("   Downloading Odoo...")
        subprocess.run(
            f'powershell -Command "$ProgressPreference = \'SilentlyContinue\'; Invoke-WebRequest -Uri \'https://github.com/odoo/odoo/archive/refs/heads/master.zip\' -OutFile \'{zip_file}\' -UseBasicParsing"',
            shell=True
        )
    
    print("   Extracting Odoo...")
    subprocess.run(
        f'powershell -Command "Expand-Archive -Path \'{zip_file}\' -DestinationPath \'{ODOO_INSTALL_DIR}\' -Force"',
        shell=True
    )
    
    # Clean up
    if zip_file.exists():
        zip_file.unlink()
    
    return find_odoo_dir()


def install_dependencies(odoo_dir):
    """Install Python dependencies."""
    print("[3/5] Installing dependencies...")
    
    requirements = odoo_dir / "requirements.txt"
    
    if requirements.exists():
        print(f"   Installing from {requirements}")
        subprocess.run(f'pip install -r "{requirements}"', shell=True)
    else:
        print("   Installing minimal requirements...")
        subprocess.run(
            'pip install werkzeug lxml psycopg2-binary Pillow requests urllib3 chardet '
            'decorator docutils gevent greenlet idna Jinja2 MarkupSafe num2words '
            'pyopenssl PyPDF2 python-dateutil pytz reportlab six qrcode openpyxl '
            'xlwt xlrd xlsxwriter',
            shell=True
        )
    
    print("   ✓ Dependencies installed")


def start_odoo(odoo_dir, config_file):
    """Start Odoo server."""
    print("[4/5] Starting Odoo server...")
    print(f"   URL: http://localhost:8069")
    
    odoo_bin = odoo_dir / "odoo-bin"
    if not odoo_bin.exists():
        odoo_bin = odoo_dir / "odoo.py"
    
    cmd = f'python "{odoo_bin}" -c "{config_file}"'
    
    # Start Odoo in background
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(odoo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print("   Waiting for Odoo to start (30 seconds)...")
    time.sleep(30)
    
    # Check if Odoo is running
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:8069", timeout=5)
        print("   ✓ Odoo is running")
    except Exception as e:
        print(f"   ⚠ Odoo may still be starting: {e}")
    
    return process


def start_mcp():
    """Start MCP server."""
    print("[5/5] Starting MCP Server...")
    print("   URL: http://localhost:8070/rpc")
    
    mcp_script = SCRIPT_DIR / "odoo_mcp.py"
    
    if not mcp_script.exists():
        print(f"   ERROR: {mcp_script} not found")
        return None
    
    # Run MCP server (this will block)
    subprocess.run(f'python "{mcp_script}"', shell=True)


def main():
    print_header("Odoo 19 + MCP Server Complete Startup")
    
    try:
        # Check PostgreSQL
        check_postgresql()
        
        # Find/extract Odoo
        odoo_dir = extract_odoo_if_needed()
        if not odoo_dir:
            print("\n❌ ERROR: Could not find Odoo source directory")
            return 1
        
        # Install dependencies
        install_dependencies(odoo_dir)
        
        # Config file
        config_file = ODOO_INSTALL_DIR / "odoo_data" / "config" / "odoo.conf"
        if not config_file.exists():
            print(f"\n❌ ERROR: Config not found: {config_file}")
            print("   Run: python odoo_setup.py")
            return 1
        
        # Start Odoo
        odoo_process = start_odoo(odoo_dir, config_file)
        
        # Start MCP (blocks)
        print("\n" + "=" * 60)
        print("  Both servers starting...")
        print("  Odoo:  http://localhost:8069")
        print("  MCP:   http://localhost:8070/rpc")
        print("  Press Ctrl+C to stop")
        print("=" * 60 + "\n")
        
        start_mcp()
        
    except KeyboardInterrupt:
        print("\n\n👋 Stopping servers...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
