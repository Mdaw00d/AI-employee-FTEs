"""
LinkedIn Login Helper - Use this to manually authenticate once.

Run this script, login normally in the browser window, then close it.
After that, linkedin_watcher.py and linkedin_approval_handler.py will use the saved session.

Usage:
    python linkedin_login.py
"""

import os
from playwright.sync_api import sync_playwright

SESSION_DIR = "./linkedin_session"
os.makedirs(SESSION_DIR, exist_ok=True)

print("=" * 60)
print("LinkedIn Login Helper")
print("=" * 60)
print(f"\nSession will be saved to: {os.path.abspath(SESSION_DIR)}")
print("\nInstructions:")
print("1. A browser window will open")
print("2. Navigate to LinkedIn and login normally")
print("3. Wait until you see your feed/messages")
print("4. Close the browser window")
print("5. Run linkedin_watcher.py or linkedin_approval_handler.py")
print("\nOpening browser in 2 seconds...")

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=SESSION_DIR,
        headless=False,
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        args=[
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--lang=en-US',
        ]
    )
    
    page = browser.new_page()
    
    print("\nOpening LinkedIn...")
    page.goto("https://www.linkedin.com/login", wait_until="networkidle")
    
    print("Login page loaded. Please sign in manually.")
    print("Close the browser when you're logged in and see your feed.\n")
    
    # Keep browser open until user closes it
    try:
        while browser.is_connected():
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    
    browser.close()

print("\nSession saved! You can now run linkedin_watcher.py or linkedin_approval_handler.py")
