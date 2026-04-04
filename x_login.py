#!/usr/bin/env python3
"""
X (Twitter) Login Helper
=========================
Run this once to log in to Twitter. Session will be saved for future posts.

Usage:
    python x_login.py
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent
SESSION_DIR = PROJECT_ROOT / "x_session"
SESSION_DIR.mkdir(exist_ok=True)

async def login():
    """Open Twitter for manual login."""
    print("=" * 60)
    print("X (TWITTER) LOGIN HELPER")
    print("=" * 60)
    print("\nA browser window will open.")
    print("1. Log in to your Twitter/X account")
    print("2. Wait until you see your home timeline")
    print("3. Close the browser when done")
    print("\nYour session will be saved for future posts.\n")
    print("Opening browser in 2 seconds...")
    await asyncio.sleep(2)
    
    async with async_playwright() as p:
        # Try system Chrome first, fallback to bundled
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        try:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                executable_path=chrome_path,
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            print("Using system Chrome")
        except Exception:
            print("System Chrome not available, using bundled Chromium")
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        print("\nNavigating to Twitter...")
        await page.goto('https://twitter.com/login', wait_until='domcontentloaded')
        
        print("\nPlease log in now. Waiting for user action...")
        print("Close the browser window when you're logged in.\n")
        
        # Wait for user to close
        try:
            await page.wait_for_event('close', timeout=300000)  # 5 min timeout
        except:
            pass
        
        await browser.close()
        
        print("\n" + "=" * 60)
        print("Login session saved!")
        print("You can now use: python orchestrator.py")
        print("Or: python x_poster.py --text 'Your tweet'")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(login())
