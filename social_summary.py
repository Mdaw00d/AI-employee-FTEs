#!/usr/bin/env python3
"""
Social Media Summary Generator - Gold Tier Integration
======================================================
Fetches recent posts and DMs from Facebook, Instagram, and X (Twitter).
Generates summary reports and writes to Briefings/{platform}_summary.md

Features:
- Fetch recent posts from each platform
- Fetch recent DMs/messages
- Generate AI-ready summary
- Write to Briefings/ directory
- Scheduled generation (hourly/daily)
- Logs to Logs/social_summary.log

Usage:
    python social_summary.py --platform facebook
    python social_summary.py --platform instagram
    python social_summary.py --platform x
    python social_summary.py --all  # Generate all platforms
"""

import os
import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
PLATFORMS = {
    'facebook': {
        'url': 'https://www.facebook.com',
        'session_dir': 'facebook_session',
        'posts_url': 'https://www.facebook.com/profile.php',
        'messages_url': 'https://www.facebook.com/messages'
    },
    'instagram': {
        'url': 'https://www.instagram.com',
        'session_dir': 'instagram_session',
        'posts_url': 'https://www.instagram.com/',
        'messages_url': 'https://www.instagram.com/direct/inbox'
    },
    'x': {
        'url': 'https://twitter.com',
        'session_dir': 'x_session',
        'posts_url': 'https://twitter.com/home',
        'messages_url': 'https://twitter.com/messages'
    }
}

LOG_DIR = PROJECT_ROOT / "Logs"
BRIEFINGS_DIR = PROJECT_ROOT / "Briefings"
LOG_DIR.mkdir(exist_ok=True)
BRIEFINGS_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "social_summary.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SocialMediaSummary:
    """Generate summaries for social media platforms."""

    def __init__(self, platform: str):
        self.platform = platform.lower()
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        if self.platform not in PLATFORMS:
            raise ValueError(f"Unknown platform: {platform}. Valid: {list(PLATFORMS.keys())}")

        self.config = PLATFORMS[self.platform]
        self.session_dir = PROJECT_ROOT / self.config['session_dir']

    async def generate(self) -> Dict[str, Any]:
        """Generate summary for the platform."""
        logger.info(f"Generating summary for {self.platform}...")

        async with async_playwright() as p:
            try:
                # Launch browser with persistent context
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=True,
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

                # Navigate to platform
                await self.page.goto(self.config['url'], wait_until='networkidle', timeout=60000)
                await asyncio.sleep(3)

                # Check login
                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.warning(f"Not logged in to {self.platform}")
                    await browser.close()
                    return {
                        'success': False,
                        'platform': self.platform,
                        'error': 'Not logged in'
                    }

                # Gather data
                posts = await self.get_recent_posts()
                messages = await self.get_recent_messages()
                notifications = await self.get_notifications()

                await browser.close()

                # Generate summary
                summary = self.create_summary(posts, messages, notifications)

                # Write to file
                self.write_summary(summary)

                return {
                    'success': True,
                    'platform': self.platform,
                    'posts_count': len(posts),
                    'messages_count': len(messages),
                    'notifications_count': len(notifications)
                }

            except Exception as e:
                logger.error(f"Error generating summary: {e}")
                return {
                    'success': False,
                    'platform': self.platform,
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in."""
        try:
            if self.platform == 'facebook':
                await self.page.wait_for_selector('[aria-label="Menu"]', timeout=10000)
            elif self.platform == 'instagram':
                await self.page.wait_for_selector('[aria-label="Home"]', timeout=10000)
            elif self.platform == 'x':
                await self.page.wait_for_selector('[data-testid="SideNav"]', timeout=10000)
            return True
        except Exception:
            return False

    async def get_recent_posts(self) -> List[Dict[str, Any]]:
        """Get recent posts from the platform."""
        posts = []
        try:
            if self.platform == 'facebook':
                posts = await self.get_facebook_posts()
            elif self.platform == 'instagram':
                posts = await self.get_instagram_posts()
            elif self.platform == 'x':
                posts = await self.get_x_posts()
        except Exception as e:
            logger.error(f"Error getting posts: {e}")
        return posts

    async def get_facebook_posts(self) -> List[Dict[str, Any]]:
        """Get recent Facebook posts."""
        posts = []
        try:
            # Navigate to profile/posts
            await self.page.goto('https://www.facebook.com/profile.php', wait_until='networkidle')
            await asyncio.sleep(3)

            # Get posts
            post_elements = await self.page.query_selector_all('[role="article"]')

            for elem in post_elements[:10]:
                try:
                    text_elem = await elem.query_selector('span[dir="auto"]')
                    if text_elem:
                        text = await text_elem.inner_text()
                        time_elem = await elem.query_selector('abbr')
                        timestamp = await time_elem.get_attribute('data-utime') if time_elem else None

                        posts.append({
                            'text': text[:500],
                            'timestamp': timestamp,
                            'platform': 'facebook'
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting Facebook posts: {e}")

        return posts

    async def get_instagram_posts(self) -> List[Dict[str, Any]]:
        """Get recent Instagram posts."""
        posts = []
        try:
            # Navigate to profile
            await self.page.goto('https://www.instagram.com/', wait_until='networkidle')
            await asyncio.sleep(3)

            # Get posts from feed
            post_elements = await self.page.query_selector_all('article')

            for elem in post_elements[:10]:
                try:
                    # Get caption
                    caption_elem = await elem.query_selector('span[dir="auto"]')
                    if caption_elem:
                        text = await caption_elem.inner_text()

                        posts.append({
                            'text': text[:500] if text else '[Image post]',
                            'platform': 'instagram'
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting Instagram posts: {e}")

        return posts

    async def get_x_posts(self) -> List[Dict[str, Any]]:
        """Get recent X (Twitter) posts."""
        posts = []
        try:
            # Navigate to profile
            await self.page.goto('https://twitter.com/home', wait_until='networkidle')
            await asyncio.sleep(3)

            # Get tweets
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')

            for elem in tweet_elements[:10]:
                try:
                    text_elem = await elem.query_selector('[data-testid="tweetText"]')
                    if text_elem:
                        text = await text_elem.inner_text()
                        time_elem = await elem.query_selector('time')
                        timestamp = await time_elem.get_attribute('datetime') if time_elem else None

                        posts.append({
                            'text': text[:500],
                            'timestamp': timestamp,
                            'platform': 'x'
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error getting X posts: {e}")

        return posts

    async def get_recent_messages(self) -> List[Dict[str, Any]]:
        """Get recent messages/DMs."""
        messages = []
        try:
            await self.page.goto(self.config['messages_url'], wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Get message elements (platform-specific)
            if self.platform == 'facebook':
                msg_elements = await self.page.query_selector_all('[role="row"]')
            elif self.platform == 'instagram':
                msg_elements = await self.page.query_selector_all('[role="listitem"]')
            elif self.platform == 'x':
                msg_elements = await self.page.query_selector_all('[data-testid="messageConversation"]')
            else:
                msg_elements = []

            for elem in msg_elements[:5]:
                try:
                    text_elem = await elem.query_selector('span[dir="auto"]')
                    if text_elem:
                        text = await text_elem.inner_text()
                        messages.append({
                            'text': text[:200],
                            'platform': self.platform
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error getting messages: {e}")

        return messages

    async def get_notifications(self) -> List[Dict[str, Any]]:
        """Get recent notifications."""
        notifications = []
        try:
            if self.platform == 'facebook':
                notif_url = 'https://www.facebook.com/notifications'
            elif self.platform == 'instagram':
                notif_url = 'https://www.instagram.com/accounts/activity'
            elif self.platform == 'x':
                notif_url = 'https://twitter.com/notifications'
            else:
                return notifications

            await self.page.goto(notif_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Get notification elements
            if self.platform == 'facebook':
                notif_elements = await self.page.query_selector_all('[role="article"]')
            elif self.platform == 'instagram':
                notif_elements = await self.page.query_selector_all('article')
            elif self.platform == 'x':
                notif_elements = await self.page.query_selector_all('[data-testid="notification"]')
            else:
                notif_elements = []

            for elem in notif_elements[:5]:
                try:
                    text_elem = await elem.query_selector('span[dir="auto"]')
                    if text_elem:
                        text = await text_elem.inner_text()
                        notifications.append({
                            'text': text[:200],
                            'platform': self.platform
                        })
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error getting notifications: {e}")

        return notifications

    def create_summary(self, posts: List[Dict], messages: List[Dict], notifications: List[Dict]) -> str:
        """Create markdown summary."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md = f"""# {self.platform.title()} Social Media Summary

**Generated:** {now}
**Platform:** {self.platform.title()}

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Recent Posts | {len(posts)} |
| Recent Messages | {len(messages)} |
| Recent Notifications | {len(notifications)} |

---

## Recent Posts

"""
        if posts:
            for i, post in enumerate(posts[:5], 1):
                md += f"### Post {i}\n\n"
                md += f"**Content:** {post.get('text', 'N/A')[:300]}\n\n"
                if post.get('timestamp'):
                    md += f"**Time:** {post['timestamp']}\n\n"
                md += "---\n\n"
        else:
            md += "*No recent posts found.*\n\n"

        md += """---

## Recent Messages

"""
        if messages:
            for i, msg in enumerate(messages[:5], 1):
                md += f"### Message {i}\n\n"
                md += f"**Content:** {msg.get('text', 'N/A')}\n\n"
                md += "---\n\n"
        else:
            md += "*No recent messages found.*\n\n"

        md += """---

## Recent Notifications

"""
        if notifications:
            for i, notif in enumerate(notifications[:5], 1):
                md += f"### Notification {i}\n\n"
                md += f"**Content:** {notif.get('text', 'N/A')}\n\n"
                md += "---\n\n"
        else:
            md += "*No recent notifications found.*\n\n"

        md += """---

## Action Items

<!-- AI agent should review and suggest actions -->

- [ ] Review any urgent messages
- [ ] Respond to customer inquiries
- [ ] Engage with important notifications
- [ ] Plan next social media posts

---

*Generated by Social Media Summary Generator - Gold Tier*
"""
        return md

    def write_summary(self, summary: str):
        """Write summary to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.platform}_summary_{timestamp}.md"
        filepath = BRIEFINGS_DIR / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(summary)

        logger.info(f"Summary written to: {filename}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Generate social media summaries')
    parser.add_argument('--platform', choices=['facebook', 'instagram', 'x'],
                        help='Platform to generate summary for')
    parser.add_argument('--all', action='store_true', help='Generate summaries for all platforms')

    args = parser.parse_args()

    if args.all:
        platforms = list(PLATFORMS.keys())
    elif args.platform:
        platforms = [args.platform]
    else:
        parser.print_help()
        return 1

    results = []
    for platform in platforms:
        summary_gen = SocialMediaSummary(platform)
        result = await summary_gen.generate()
        results.append(result)
        await asyncio.sleep(2)  # Delay between platforms

    print("\n" + "=" * 50)
    print("SUMMARY GENERATION RESULTS")
    print("=" * 50)
    for result in results:
        status = "✓" if result.get('success') else "✗"
        print(f"{status} {result['platform']}: {result.get('posts_count', 0)} posts, "
              f"{result.get('messages_count', 0)} messages, "
              f"{result.get('notifications_count', 0)} notifications")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
