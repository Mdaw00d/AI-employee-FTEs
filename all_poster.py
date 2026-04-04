#!/usr/bin/env python3
"""
All Platforms Poster - Unified Script
======================================
Posts to Facebook, Instagram, and X (Twitter) simultaneously.

Usage:
    python all_poster.py --platforms facebook,instagram,x --text "Hello World" --dry-run
    python all_poster.py --platforms all --text "New post!" --image photo.jpg
    python all_poster.py --platforms facebook,x --text "Cross-posting"

Platforms: facebook, instagram, x, all
"""

import os
import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
PLATFORMS_CONFIG = {
    'facebook': {
        'url': 'https://www.facebook.com',
        'session_dir': 'facebook_session',
        'post_url': 'https://www.facebook.com',
        'login_selector': '[aria-label="Menu"]'
    },
    'instagram': {
        'url': 'https://www.instagram.com',
        'session_dir': 'instagram_session',
        'post_url': 'https://www.instagram.com/create/details/',
        'login_selector': '[aria-label="Home"]'
    },
    'x': {
        'url': 'https://twitter.com',
        'session_dir': 'x_session',
        'post_url': 'https://twitter.com/home',
        'login_selector': '[data-testid="SideNav"]'
    }
}

LOG_DIR = PROJECT_ROOT / "Logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "all_poster.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PlatformPoster:
    """Base poster for a specific platform."""

    def __init__(self, platform: str, dry_run: bool = False):
        self.platform = platform.lower()
        self.dry_run = dry_run
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        if self.platform not in PLATFORMS_CONFIG:
            raise ValueError(f"Unknown platform: {platform}. Valid: {list(PLATFORMS_CONFIG.keys())}")

        self.config = PLATFORMS_CONFIG[self.platform]
        self.session_dir = PROJECT_ROOT / self.config['session_dir']
        self.session_dir.mkdir(exist_ok=True)

    async def post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post content to the platform."""
        logger.info(f"Posting to {self.platform} (dry_run={self.dry_run})")

        if self.dry_run:
            return {
                'success': True,
                'dry_run': True,
                'platform': self.platform,
                'text': text,
                'image': image_path,
                'message': 'Dry run - no post made'
            }

        # Instagram requires an image
        if self.platform == 'instagram' and not image_path:
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Instagram requires an image'
            }

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )

                if browser.pages:
                    self.page = browser.pages[0]
                else:
                    self.page = await browser.new_page()

                self.context = browser

                logger.info(f"Navigating to {self.config['url']}...")
                await self.page.goto(self.config['url'], wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(5)

                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.error(f"Not logged in to {self.platform}. Please login manually.")
                    logger.info("Waiting 60 seconds for manual login...")
                    for i in range(12):
                        await asyncio.sleep(5)
                        logger.info(f"Checking login status... ({(i+1)*5}s/60s)")
                        is_logged_in = await self.check_login()
                        if is_logged_in:
                            logger.info("Login detected! Continuing...")
                            break

                    if not is_logged_in:
                        logger.error(f"Still not logged in to {self.platform}")
                        await asyncio.sleep(5)
                        await browser.close()
                        return {
                            'success': False,
                            'platform': self.platform,
                            'error': 'Not logged in'
                        }

                result = await self.make_post(text, image_path)
                await browser.close()

                return result

            except Exception as e:
                logger.error(f"Error posting to {self.platform}: {e}")
                return {
                    'success': False,
                    'platform': self.platform,
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in."""
        selectors = [self.config.get('login_selector', '')]
        
        # Add platform-specific fallback selectors
        if self.platform == 'facebook':
            selectors.extend([
                '[aria-label="Home"]',
                'a[href="/profile"]',
                '[data-pagelet="MainFeed"]',
            ])
        elif self.platform == 'instagram':
            selectors.extend([
                '[aria-label="Profile"]',
                'a[href*="/profile"]',
                'svg[aria-label="Home"]',
            ])
        elif self.platform == 'x':
            selectors.extend([
                '[role="navigation"]',
                'a[href="/home"]',
                '[data-testid="AppTabBar"]',
            ])
        
        for selector in selectors:
            if not selector:
                continue
            try:
                await self.page.wait_for_selector(selector, timeout=8000)
                logger.info(f"Login detected via: {selector}")
                return True
            except Exception:
                continue
        
        logger.warning(f"No login indicators found for {self.platform}")
        return False

    async def make_post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Make the actual post based on platform."""
        if self.platform == 'facebook':
            return await self.post_facebook(text, image_path)
        elif self.platform == 'instagram':
            return await self.post_instagram(text, image_path)
        elif self.platform == 'x':
            return await self.post_x(text, image_path)
        else:
            return {'success': False, 'platform': self.platform, 'error': 'Unknown platform'}

    async def post_facebook(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to Facebook."""
        logger.info("Posting to Facebook...")

        await self.page.goto('https://www.facebook.com', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # Click on post box with multiple selectors
        post_box_selectors = [
            '[aria-label="What\'s on your mind?"]',
            '[placeholder="What\'s on your mind?"]',
            'div[role="button"]:has-text("What\'s on your mind?")',
            '[data-testid="create_post"]',
        ]
        
        for selector in post_box_selectors:
            try:
                await self.page.click(selector, timeout=8000)
                logger.info(f"Clicked post box: {selector}")
                await asyncio.sleep(2)
                break
            except Exception:
                continue

        # Type content
        await self.page.keyboard.type(text, delay=50)
        await asyncio.sleep(1)

        # Upload image if provided
        if image_path and os.path.exists(image_path):
            logger.info(f"Uploading image: {image_path}")
            try:
                file_input = await self.page.query_selector('input[type="file"][accept*="image"]')
                if file_input:
                    await file_input.set_input_files(image_path)
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"Could not upload image: {e}")

        # Click Post button with multiple selectors
        post_selectors = [
            '[aria-label="Post"]',
            'button:has-text("Post")',
            'button:has-text("Share")',
            'button[type="submit"]',
        ]
        
        for selector in post_selectors:
            try:
                post_button = await self.page.wait_for_selector(selector, state='enabled', timeout=8000)
                if post_button:
                    await post_button.click()
                    logger.info("Facebook post submitted!")
                    await asyncio.sleep(3)
                    return {
                        'success': True,
                        'platform': 'facebook',
                        'text': text,
                        'image': image_path,
                        'message': 'Post submitted successfully',
                        'timestamp': datetime.now().isoformat()
                    }
            except Exception:
                continue
        
        # JavaScript fallback
        try:
            logger.info("Attempting JavaScript click for Facebook post...")
            await self.page.evaluate('''() => {
                const buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    const text = btn.textContent || btn.getAttribute('aria-label') || '';
                    if ((text.includes('Post') || text.includes('Share')) && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            await asyncio.sleep(3)
            return {
                'success': True,
                'platform': 'facebook',
                'text': text,
                'image': image_path,
                'message': 'Post attempted via JavaScript',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Could not submit Facebook post: {e}")
            return {'success': False, 'platform': 'facebook', 'error': str(e)}

    async def post_instagram(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to Instagram."""
        logger.info("Posting to Instagram...")

        if not image_path:
            return {'success': False, 'platform': 'instagram', 'error': 'Instagram requires an image'}

        await self.page.goto('https://www.instagram.com/create/details/', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)

        # Upload image
        file_input_selectors = [
            'input[type="file"]',
            'input[type="file"][accept*="image"]',
        ]
        
        for selector in file_input_selectors:
            try:
                file_input = await self.page.query_selector(selector)
                if file_input:
                    await file_input.set_input_files(image_path)
                    logger.info(f"Uploaded image via: {selector}")
                    await asyncio.sleep(4)
                    break
            except Exception:
                continue

        # Click Next
        next_selectors = [
            'button:has-text("Next")',
            '[aria-label="Next"]',
        ]
        
        for selector in next_selectors:
            try:
                await self.page.click(selector, timeout=8000)
                logger.info(f"Clicked Next: {selector}")
                await asyncio.sleep(2)
                break
            except Exception:
                continue

        # Add caption
        caption_selectors = [
            'textarea[aria-label*="caption"]',
            'textarea[placeholder*="caption"]',
            'textarea',
        ]
        
        for selector in caption_selectors:
            try:
                caption_area = await self.page.query_selector(selector)
                if caption_area:
                    await caption_area.fill(text)
                    logger.info(f"Added caption via: {selector}")
                    await asyncio.sleep(1)
                    break
            except Exception:
                continue

        # Click Share
        share_selectors = [
            'button:has-text("Share")',
            'button:has-text("Post")',
            '[aria-label="Share"]',
        ]
        
        for selector in share_selectors:
            try:
                share_button = await self.page.wait_for_selector(selector, state='enabled', timeout=8000)
                if share_button:
                    await share_button.click()
                    logger.info("Instagram post submitted!")
                    await asyncio.sleep(3)
                    return {
                        'success': True,
                        'platform': 'instagram',
                        'text': text,
                        'image': image_path,
                        'message': 'Post submitted successfully',
                        'timestamp': datetime.now().isoformat()
                    }
            except Exception:
                continue
        
        # JavaScript fallback
        try:
            logger.info("Attempting JavaScript click for Instagram share...")
            await self.page.evaluate('''() => {
                const buttons = document.querySelectorAll('button, div[role="button"]');
                for (let btn of buttons) {
                    const text = btn.textContent || btn.getAttribute('aria-label') || '';
                    if ((text.includes('Share') || text.includes('Post')) && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            await asyncio.sleep(3)
            return {
                'success': True,
                'platform': 'instagram',
                'text': text,
                'image': image_path,
                'message': 'Post attempted via JavaScript',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Could not submit Instagram post: {e}")
            return {'success': False, 'platform': 'instagram', 'error': str(e)}

    async def post_x(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to X (Twitter)."""
        logger.info("Posting to X (Twitter)...")

        if len(text) > 280:
            logger.warning(f"Text exceeds 280 character limit ({len(text)} characters)")

        await self.page.goto('https://twitter.com/home', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # Find tweet box
        tweet_selectors = [
            '[data-testid="tweetTextarea_0"]',
            '[role="textbox"][aria-label*="Tweet"]',
            '[aria-label*="Tweet"]',
        ]
        
        tweet_box_found = False
        for selector in tweet_selectors:
            try:
                tweet_box = await self.page.query_selector(selector)
                if tweet_box:
                    await tweet_box.click()
                    await asyncio.sleep(1)
                    await self.page.keyboard.type(text, delay=50)
                    await asyncio.sleep(2)
                    tweet_box_found = True
                    logger.info(f"Typed tweet via: {selector}")
                    break
            except Exception:
                continue
        
        if not tweet_box_found:
            logger.error("Could not find tweet box")
            return {'success': False, 'platform': 'x', 'error': 'Could not find tweet box'}

        # Upload image if provided
        if image_path and os.path.exists(image_path):
            logger.info(f"Uploading image: {image_path}")
            try:
                file_input = await self.page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(image_path)
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"Could not upload image: {e}")

        # Click Post button
        post_selectors = [
            '[data-testid="tweetButton"]',
            '[data-testid="tweetButtonInline"]',
            'button[aria-label*="Tweet"]',
            'button:has-text("Post")',
            'button:has-text("Tweet")',
        ]
        
        for selector in post_selectors:
            try:
                post_button = await self.page.wait_for_selector(selector, state='enabled', timeout=8000)
                if post_button:
                    await post_button.click()
                    logger.info("X (Twitter) post submitted!")
                    await asyncio.sleep(3)
                    return {
                        'success': True,
                        'platform': 'x',
                        'text': text,
                        'image': image_path,
                        'message': 'Post submitted successfully',
                        'timestamp': datetime.now().isoformat()
                    }
            except Exception:
                continue
        
        # JavaScript fallback
        try:
            logger.info("Attempting JavaScript click for X post...")
            await self.page.evaluate('''() => {
                const buttons = document.querySelectorAll('button');
                for (let btn of buttons) {
                    const text = btn.textContent || btn.getAttribute('aria-label') || '';
                    if ((text.includes('Tweet') || text.includes('Post')) && !btn.disabled) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            await asyncio.sleep(3)
            return {
                'success': True,
                'platform': 'x',
                'text': text,
                'image': image_path,
                'message': 'Post attempted via JavaScript',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Could not submit X post: {e}")
            return {'success': False, 'platform': 'x', 'error': str(e)}


async def post_to_platforms(platforms: List[str], text: str, image_path: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Post to multiple platforms."""
    results = {}

    for platform in platforms:
        logger.info(f"Posting to {platform}...")
        poster = PlatformPoster(platform, dry_run=dry_run)
        result = await poster.post(text, image_path)
        results[platform] = result
        await asyncio.sleep(2)  # Delay between platforms

    return results


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Post to multiple social media platforms')
    parser.add_argument('--platforms', required=True,
                        help='Platforms to post to (comma-separated: facebook,instagram,x or "all")')
    parser.add_argument('--text', required=True, help='Text content to post')
    parser.add_argument('--image', help='Path to image file (optional)')
    parser.add_argument('--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    # Parse platforms
    if args.platforms.lower() == 'all':
        platforms = list(PLATFORMS_CONFIG.keys())
    else:
        platforms = [p.strip().lower() for p in args.platforms.split(',')]

    # Validate platforms
    for platform in platforms:
        if platform not in PLATFORMS_CONFIG:
            print(f"Error: Unknown platform '{platform}'. Valid: {list(PLATFORMS_CONFIG.keys())}")
            return 1

    print(f"\nPosting to: {', '.join(platforms)}")
    print(f"Text: {args.text[:50]}{'...' if len(args.text) > 50 else ''}")
    if args.image:
        print(f"Image: {args.image}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 50)

    results = await post_to_platforms(platforms, args.text, args.image, dry_run=args.dry_run)

    print("\n" + "=" * 50)
    print("ALL PLATFORMS POST RESULTS")
    print("=" * 50)
    print(json.dumps(results, indent=2))
    print("=" * 50)

    # Summary
    success_count = sum(1 for r in results.values() if r.get('success'))
    print(f"\nSummary: {success_count}/{len(results)} platforms successful")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
