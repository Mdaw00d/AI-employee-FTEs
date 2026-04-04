#!/usr/bin/env python3
"""
X (Twitter) Poster - Standalone Script
=======================================
Posts to X (Twitter) using Playwright browser automation with persistent sessions.

Usage:
    python x_poster.py --text "Tweet content" --dry-run
    python x_poster.py --text "New post!" --image path/to/image.jpg

Note: X has a character limit of 280 characters for tweets.
"""

import os
import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
X_CONFIG = {
    'url': 'https://twitter.com',
    'session_dir': 'x_session',
    'post_url': 'https://twitter.com/home'
}

LOG_DIR = PROJECT_ROOT / "Logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "x_poster.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class XPoster:
    """Post to X (Twitter)."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_dir = PROJECT_ROOT / X_CONFIG['session_dir']
        self.session_dir.mkdir(exist_ok=True)

    async def post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post content to X (Twitter)."""
        logger.info(f"Posting to X (Twitter) (dry_run={self.dry_run})")

        # Check character limit
        if len(text) > 280:
            logger.warning(f"Text exceeds 280 character limit ({len(text)} characters)")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would post to X (Twitter):")
            logger.info(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")
            if image_path:
                logger.info(f"  Image: {image_path}")
            return {
                'success': True,
                'dry_run': True,
                'platform': 'x',
                'text': text,
                'image': image_path,
                'message': 'Dry run - no post made'
            }

        async with async_playwright() as p:
            try:
                # Try launching with system Chrome first, fallback to bundled
                chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                try:
                    browser = await p.chromium.launch_persistent_context(
                        user_data_dir=str(self.session_dir),
                        executable_path=chrome_path,
                        headless=False,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                        ]
                    )
                    logger.info("Using system Chrome")
                except Exception:
                    logger.info("System Chrome not available, using bundled Chromium")
                    browser = await p.chromium.launch_persistent_context(
                        user_data_dir=str(self.session_dir),
                        headless=False,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--disable-dev-shm-usage',
                            '--no-sandbox',
                        ]
                    )

                if browser.pages:
                    self.page = browser.pages[0]
                else:
                    self.page = await browser.new_page()

                self.context = browser

                # Navigate to X - use domcontentloaded since networkidle times out on X
                logger.info("Navigating to X (Twitter)...")
                await self.page.goto(X_CONFIG['url'], wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(8)  # Wait for page to fully render

                # Check login with retry logic
                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.warning("Not logged in yet. The browser window is open - please login to X (Twitter).")
                    logger.info("Waiting 120 seconds for manual login...")
                    for i in range(24):
                        await asyncio.sleep(5)
                        logger.info(f"Checking login status... ({(i+1)*5}s/120s)")
                        is_logged_in = await self.check_login()
                        if is_logged_in:
                            logger.info("Login detected! Continuing...")
                            break

                    if not is_logged_in:
                        logger.error("Still not logged in after 120 seconds.")
                        await asyncio.sleep(5)
                        await browser.close()
                        return {
                            'success': False,
                            'platform': 'x',
                            'error': 'Not logged in'
                        }

                # Make the post
                result = await self.make_post(text, image_path)

                await browser.close()

                return result

            except Exception as e:
                logger.error(f"Error posting: {e}")
                return {
                    'success': False,
                    'platform': 'x',
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in using multiple selectors."""
        # First check if we're on the sign-in page
        try:
            sign_in = await self.page.query_selector('text="Sign in to X"')
            if sign_in:
                logger.info("Sign-in page detected, not logged in")
                return False
        except Exception:
            pass

        selectors = [
            '[data-testid="SideNav"]',
            '[data-testid="tweetTextarea_0"]',
            'a[href="/home"]',
            '[data-testid="AppTabBar"]',
            '[aria-label*="Home"]',
        ]

        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=5000)
                logger.info(f"Login detected via selector: {selector}")
                return True
            except Exception:
                continue

        logger.warning("No login indicators found with any selector")
        return False

    async def make_post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Make the actual post."""
        logger.info("Posting to X (Twitter)...")

        # Navigate to home - already logged in, fast navigation
        await self.page.goto('https://twitter.com/home', wait_until='domcontentloaded', timeout=15000)
        await asyncio.sleep(1)

        # Click tweet box to activate
        try:
            await self.page.click('[data-testid="tweetTextarea_0"]', timeout=5000)
            await asyncio.sleep(1)
            logger.info("Tweet box clicked")
        except:
            logger.warning("Could not click tweet box, proceeding anyway")

        # Type the tweet using Playwright's keyboard
        try:
            await self.page.keyboard.type(text, delay=30)
            await asyncio.sleep(1)
            logger.info("Tweet text entered")
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return {'success': False, 'platform': 'x', 'error': str(e)}

        # Wait for button to enable
        await asyncio.sleep(1)

        # Click Post button - try native click first, then JS fallback
        try:
            await self.page.click('[data-testid="tweetButton"]', timeout=3000)
            logger.info("Post button clicked via Playwright!")
            await asyncio.sleep(2)
            return {
                'success': True,
                'platform': 'x',
                'text': text,
                'image': image_path,
                'message': 'Post submitted successfully',
                'url': self.page.url,
                'timestamp': datetime.now().isoformat()
            }
        except:
            logger.warning("Playwright click failed, trying JS")
            # JS fallback - find and click the button
            clicked = await self.page.evaluate('''() => {
                const allBtns = document.querySelectorAll('button, [role="button"]');
                for (const btn of allBtns) {
                    if (btn.textContent.includes('Post') && btn.offsetHeight > 0) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            if clicked:
                logger.info("Post button clicked via JS!")
                await asyncio.sleep(2)
                return {
                    'success': True,
                    'platform': 'x',
                    'text': text,
                    'image': image_path,
                    'message': 'Post submitted successfully',
                    'url': self.page.url,
                    'timestamp': datetime.now().isoformat()
                }

        return {'success': False, 'platform': 'x', 'error': 'Could not submit post'}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Post to X (Twitter)')
    parser.add_argument('--text', required=True, help='Text content to tweet')
    parser.add_argument('--image', help='Path to image file (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    poster = XPoster(dry_run=args.dry_run)
    result = await poster.post(args.text, args.image)

    print("\n" + "=" * 50)
    print("X (TWITTER) POST RESULT")
    print("=" * 50)
    print(json.dumps(result, indent=2))
    print("=" * 50)

    return 0 if result.get('success') else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
