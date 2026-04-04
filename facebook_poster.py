#!/usr/bin/env python3
"""
Facebook Poster - Standalone Script
====================================
Posts to Facebook using Playwright browser automation with persistent sessions.

Usage:
    python facebook_poster.py --text "Hello World" --dry-run
    python facebook_poster.py --text "New post!" --image path/to/image.jpg
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
FACEBOOK_CONFIG = {
    'url': 'https://www.facebook.com',
    'session_dir': 'facebook_session',
    'post_url': 'https://www.facebook.com'
}

LOG_DIR = PROJECT_ROOT / "Logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "facebook_poster.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FacebookPoster:
    """Post to Facebook."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_dir = PROJECT_ROOT / FACEBOOK_CONFIG['session_dir']
        self.session_dir.mkdir(exist_ok=True)

    async def post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post content to Facebook."""
        logger.info(f"Posting to Facebook (dry_run={self.dry_run})")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would post to Facebook:")
            logger.info(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")
            if image_path:
                logger.info(f"  Image: {image_path}")
            return {
                'success': True,
                'dry_run': True,
                'platform': 'facebook',
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

                # Navigate to Facebook - use domcontentloaded since networkidle times out
                logger.info("Navigating to Facebook...")
                await self.page.goto(FACEBOOK_CONFIG['url'], wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)

                # Check login
                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.warning("Not logged in yet. The browser window is open - please login to Facebook.")
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
                            'platform': 'facebook',
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
                    'platform': 'facebook',
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in."""
        selectors = [
            '[aria-label="Menu"]',
            '[aria-label="Home"]',
            'a[href="/profile"]',
            '[data-pagelet="MainFeed"]',
        ]

        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=8000)
                logger.info(f"Login detected via: {selector}")
                return True
            except Exception:
                continue

        logger.warning("No login indicators found")
        return False

    async def make_post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Make the actual post."""
        logger.info("Posting to Facebook...")

        # Navigate to home page
        await self.page.goto('https://www.facebook.com', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Click on "What's on your mind?" box
        try:
            await self.page.click('span:has-text("What\'s on your mind")', timeout=5000)
            await asyncio.sleep(2)
            logger.info("Clicked post box")
        except Exception as e:
            logger.error(f"Could not click post box: {e}")
            return {'success': False, 'platform': 'facebook', 'error': 'Could not open post composer'}

        # Type the post content using keyboard
        try:
            logger.info(f"Typing post content ({len(text)} chars)...")
            await self.page.keyboard.type(text, delay=30)
            await asyncio.sleep(2)
            logger.info("Text entry complete")
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return {'success': False, 'platform': 'facebook', 'error': str(e)}

        # Take screenshot to verify content
        screenshot_path = os.path.join(LOG_DIR, f'fb_before_post_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        await self.page.screenshot(path=screenshot_path)
        logger.info(f"Screenshot saved: {screenshot_path}")

        # Find and click the actual Post button
        post_clicked = False

        # Strategy 1: Try to find enabled Post button in dialog
        try:
            # Wait for Post button to appear and be enabled
            post_btn = await self.page.wait_for_selector(
                'div[aria-label="Post"][role="button"]:not([aria-disabled="true"])',
                timeout=10000
            )
            if post_btn:
                await post_btn.click()
                logger.info("Clicked enabled Post button!")
                post_clicked = True
        except Exception as e:
            logger.warning(f"Strategy 1 failed: {e}")

        # Strategy 2: Find Post button by text content
        if not post_clicked:
            try:
                # Look for Post button in the dialog
                buttons = await self.page.query_selector_all('[role="button"]')
                for btn in buttons:
                    text_content = await btn.inner_text()
                    if text_content.strip().lower() == 'post':
                        aria_disabled = await btn.get_attribute('aria-disabled')
                        if aria_disabled != 'true':
                            await btn.click()
                            logger.info("Clicked Post button (strategy 2)")
                            post_clicked = True
                            break
            except Exception as e:
                logger.warning(f"Strategy 2 failed: {e}")

        # Strategy 3: Try Ctrl+Enter shortcut
        if not post_clicked:
            try:
                await self.page.keyboard.press('Control+Enter')
                logger.info("Pressed Ctrl+Enter to submit")
                post_clicked = True
            except Exception as e:
                logger.warning(f"Ctrl+Enter failed: {e}")

        if post_clicked:
            # Wait and verify post was actually submitted
            await asyncio.sleep(5)

            # Check if dialog is still open - if not, post was submitted
            dialog_open = await self.page.query_selector('[role="dialog"]')
            if dialog_open is None:
                logger.info("Dialog closed - post submitted!")
                return {
                    'success': True,
                    'platform': 'facebook',
                    'text': text,
                    'image': image_path,
                    'message': 'Post submitted and verified',
                    'timestamp': datetime.now().isoformat()
                }

            # Wait a bit longer for slow connections
            await asyncio.sleep(3)
            
            # Check again
            dialog_open = await self.page.query_selector('[role="dialog"]')
            if dialog_open is None:
                logger.info("Dialog closed after wait - post submitted!")
                return {
                    'success': True,
                    'platform': 'facebook',
                    'text': text,
                    'image': image_path,
                    'message': 'Post submitted and verified',
                    'timestamp': datetime.now().isoformat()
                }

            # Try clicking Post button again
            try:
                post_btn2 = await self.page.wait_for_selector(
                    'div[aria-label="Post"][role="button"]:not([aria-disabled="true"])',
                    timeout=5000
                )
                if post_btn2:
                    await post_btn2.click()
                    logger.info("Clicked Post button again")
                    await asyncio.sleep(5)
                    
                    dialog_open = await self.page.query_selector('[role="dialog"]')
                    if dialog_open is None:
                        return {
                            'success': True,
                            'platform': 'facebook',
                            'text': text,
                            'image': image_path,
                            'message': 'Post submitted on second attempt',
                            'timestamp': datetime.now().isoformat()
                        }
            except:
                pass

            # Take screenshot to see current state
            fail_ss = os.path.join(LOG_DIR, f'fb_post_fail_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
            await self.page.screenshot(path=fail_ss)
            logger.error(f"Post may not have been submitted. Screenshot: {fail_ss}")
            return {'success': False, 'platform': 'facebook', 'error': 'Post not submitted - dialog still open'}

        return {
            'success': False,
            'platform': 'facebook',
            'error': 'Could not find Post button'
        }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Post to Facebook')
    parser.add_argument('--text', required=True, help='Text content to post')
    parser.add_argument('--image', help='Path to image file (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    poster = FacebookPoster(dry_run=args.dry_run)
    result = await poster.post(args.text, args.image)

    print("\n" + "=" * 50)
    print("FACEBOOK POST RESULT")
    print("=" * 50)
    print(json.dumps(result, indent=2))
    print("=" * 50)

    return 0 if result.get('success') else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
