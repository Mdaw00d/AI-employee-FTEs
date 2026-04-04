#!/usr/bin/env python3
"""
Initialize Odoo Database
========================
Creates the database schema for Odoo.

Usage:
    python init_odoo_db.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Add PostgreSQL to PATH
PG_PATH = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin")
if PG_PATH.exists():
    os.environ["PATH"] = str(PG_PATH) + os.pathsep + os.environ.get("PATH", "")

ODOO_DIR = Path(r"C:\Odoo19\odoo-master")
CONFIG_FILE = Path(r"C:\Odoo19\odoo_data\config\odoo.conf")

def main():
    print("=" * 60)
    print("  Odoo Database Initialization")
    print("=" * 60)
    print()
    print("This will initialize the Odoo database schema.")
    print("This may take 2-5 minutes...")
    print()
    
    # Stop any running Odoo instances
    print("Stopping any running Odoo instances...")
    subprocess.run('taskkill /F /FI "WINDOWTITLE eq Odoo*" /T 2>nul', shell=True)
    time.sleep(2)
    
    # Initialize database
    print("Initializing database...")
    print("(Look for 'Odoo is running' message)")
    print()
    
    os.chdir(ODOO_DIR)
    
    # Run Odoo with init flag
    cmd = f'python odoo-bin -c "{CONFIG_FILE}" -d odoo_db --init all --stop-after-init --without-demo all'
    
    try:
        subprocess.run(cmd, shell=True, timeout=300)
        print()
        print("=" * 60)
        print("  Database Initialization Complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Start Odoo: cd C:\\Odoo19\\odoo-master && python odoo-bin -c C:\\Odoo19\\odoo_data\\config\\odoo.conf")
        print("  2. Start MCP:  python odoo_mcp.py")
        print()
    except subprocess.TimeoutExpired:
        print()
        print("Initialization timed out. Check logs for errors.")
        print(f"Log file: {Path('C:\\Odoo19\\odoo_data\\logs\\odoo.log')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
