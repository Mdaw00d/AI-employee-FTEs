#!/usr/bin/env python3
"""
Instagram Poster - Standalone Script
=====================================
Posts to Instagram using Playwright browser automation with persistent sessions.

Usage:
    python instagram_poster.py --text "New post!" --image path/to/image.jpg --dry-run
    python instagram_poster.py --text "Caption here" --image photo.jpg

Note: Instagram requires an image for posting.
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
INSTAGRAM_CONFIG = {
    'url': 'https://www.instagram.com',
    'session_dir': 'instagram_session',
    'post_url': 'https://www.instagram.com/create/details/'
}

LOG_DIR = PROJECT_ROOT / "Logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "instagram_poster.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class InstagramPoster:
    """Post to Instagram."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_dir = PROJECT_ROOT / INSTAGRAM_CONFIG['session_dir']
        self.session_dir.mkdir(exist_ok=True)

    async def post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post content to Instagram."""
        logger.info(f"Posting to Instagram (dry_run={self.dry_run})")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would post to Instagram:")
            logger.info(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")
            if image_path:
                logger.info(f"  Image: {image_path}")
            return {
                'success': True,
                'dry_run': True,
                'platform': 'instagram',
                'text': text,
                'image': image_path,
                'message': 'Dry run - no post made'
            }

        if not image_path:
            logger.error("Instagram requires an image")
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Instagram requires an image'
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

                # Navigate to Instagram - use domcontentloaded since networkidle times out
                logger.info("Navigating to Instagram...")
                await self.page.goto(INSTAGRAM_CONFIG['url'], wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(5)

                # Check login
                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.warning("Not logged in yet. The browser window is open - please login to Instagram.")
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
                            'platform': 'instagram',
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
                    'platform': 'instagram',
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in."""
        # Check if on login page
        try:
            login_text = await self.page.query_selector('text="Log in"')
            if login_text:
                logger.info("Login page detected, not logged in")
                return False
        except Exception:
            pass

        selectors = [
            '[aria-label="Home"]',
            '[aria-label="Profile"]',
            'a[href*="/profile"]',
            'svg[aria-label="Home"]',
            'svg[aria-label="New post"]',
        ]

        for selector in selectors:
            try:
                await self.page.wait_for_selector(selector, timeout=5000)
                logger.info(f"Login detected via: {selector}")
                return True
            except Exception:
                continue

        logger.warning("No login indicators found")
        return False

    async def make_post(self, text: str, image_path: str) -> Dict[str, Any]:
        """Make the actual post."""
        logger.info("Posting to Instagram...")

        # Navigate to home
        await self.page.goto('https://www.instagram.com/', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(1)

        # Dismiss popups quickly
        try:
            await self.page.keyboard.press('Escape')
        except Exception:
            pass

        # Click "+" button
        try:
            plus_btn = await self.page.query_selector('svg[aria-label="New post"]')
            if plus_btn and await plus_btn.is_visible():
                await plus_btn.click()
                logger.info("Clicked + button")
                await asyncio.sleep(1)
        except Exception:
            pass

        # Upload image
        file_input_uploaded = False
        for selector in ['input[type="file"]', 'input[type="file"][accept*="image"]']:
            try:
                file_input = await self.page.query_selector(selector)
                if file_input:
                    await file_input.set_input_files(image_path)
                    logger.info(f"Uploaded image")
                    file_input_uploaded = True
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

        if not file_input_uploaded:
            return {'success': False, 'platform': 'instagram', 'error': 'Could not upload image'}

        # Click Next buttons until we see the caption textarea (Share screen)
        for step in range(3):
            # Check if caption textarea exists
            textarea = await self.page.query_selector('textarea')
            if textarea:
                logger.info(f"Found caption textarea after {step} Next clicks")
                break
            
            # Click Next
            try:
                clicked = await self.page.evaluate('''() => {
                    const btns = document.querySelectorAll('div[role="button"], button');
                    for (const b of btns) {
                        const t = b.textContent || b.getAttribute('aria-label') || '';
                        if (t.trim() === 'Next' && b.offsetHeight > 0) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                if clicked:
                    logger.info(f"Clicked Next (step {step+1}) via JS")
                    await asyncio.sleep(2)
                else:
                    logger.info(f"No Next button found at step {step+1}")
                    break
            except:
                break

        # Wait for caption screen to load
        await asyncio.sleep(1)

        # Add caption - use JS for speed
        try:
            js_text = text.replace("'", "\\'").replace("\n", "\\n")
            await self.page.evaluate(f'''() => {{
                const ta = document.querySelector('textarea');
                if (ta) {{
                    ta.focus();
                    ta.innerText = `{js_text}`;
                    ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            }}''')
            await asyncio.sleep(0.5)
            logger.info("Caption added via JS")
        except:
            pass

        # Wait a moment for the Share button to be ready
        await asyncio.sleep(2)

        # Click Share button - the one in the create flow header (not feed posts)
        try:
            clicked = await self.page.evaluate('''() => {
                // The create flow Share button is typically at the top right
                // It's NOT inside an <article> element (those are feed posts)
                const allDivs = document.querySelectorAll('div[role="button"]');
                for (const div of allDivs) {
                    const text = (div.textContent || div.getAttribute('aria-label') || '').trim();
                    if (text === 'Share' && div.offsetHeight > 0) {
                        // Make sure it's NOT inside a feed post (article element)
                        let parent = div.parentElement;
                        let isInFeed = false;
                        for (let i = 0; i < 15 && parent; i++) {
                            if (parent.tagName === 'ARTICLE') {
                                isInFeed = true;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        
                        // We want the Share button that's NOT in a feed post
                        if (!isInFeed) {
                            // Get screen position and use dispatchEvent for real click
                            const rect = div.getBoundingClientRect();
                            div.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 }));
                            div.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 }));
                            div.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: rect.left + rect.width/2, clientY: rect.top + rect.height/2 }));
                            return 'clicked';
                        }
                    }
                }
                return 'not_found';
            }''')
            
            if clicked == 'clicked':
                logger.info("Share button clicked via JS (PointerEvent)!")
                
                # Wait longer for Instagram to process the post
                # Check for success message "Your post has been shared"
                post_submitted = False
                for i in range(30):
                    await asyncio.sleep(2)
                    
                    # Check 1: Dialog closed
                    dialog = await self.page.query_selector('[role="dialog"], [role="presentation"]')
                    if dialog is None:
                        logger.info("Dialog closed - post submitted!")
                        post_submitted = True
                        break
                    
                    # Check 2: Success message visible
                    try:
                        page_text = await self.page.evaluate('() => document.body.innerText')
                        if 'Your post has been shared' in page_text or 'Post created' in page_text or 'shared' in page_text.lower():
                            logger.info("Success message detected!")
                            post_submitted = True
                            break
                    except:
                        pass
                    
                    if i % 5 == 0:
                        logger.info(f"Waiting for post processing... ({(i+1)*2}s)")
                
                if post_submitted:
                    # Wait a few more seconds to ensure everything settles
                    await asyncio.sleep(3)
                    return {
                        'success': True,
                        'platform': 'instagram',
                        'text': text,
                        'image': image_path,
                        'message': 'Post submitted and verified',
                        'timestamp': datetime.now().isoformat()
                    }
                
                logger.warning("Dialog still open after 60s wait")
        except Exception as e:
            logger.warning(f"JS click failed: {e}")

        # Take screenshot to see current state
        fail_ss = os.path.join(LOG_DIR, f'ig_post_fail_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
        await self.page.screenshot(path=fail_ss)
        logger.error(f"Post not submitted. Screenshot: {fail_ss}")
        return {'success': False, 'platform': 'instagram', 'error': 'Could not submit post'}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Post to Instagram')
    parser.add_argument('--text', required=True, help='Text content/caption to post')
    parser.add_argument('--image', required=True, help='Path to image file (required for Instagram)')
    parser.add_argument('--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    poster = InstagramPoster(dry_run=args.dry_run)
    result = await poster.post(args.text, args.image)

    print("\n" + "=" * 50)
    print("INSTAGRAM POST RESULT")
    print("=" * 50)
    print(json.dumps(result, indent=2))
    print("=" * 50)

    return 0 if result.get('success') else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
