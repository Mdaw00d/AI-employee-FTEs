#!/usr/bin/env python3
"""
X (Twitter) Watcher - Gold Tier Social Media Integration
=========================================================
Monitors X (Twitter) for new mentions, DMs, and notifications with keywords.
Uses Playwright with persistent session for authentication.

Features:
- Persistent browser session (./x_session)
- Monitor mentions, DMs, and notifications
- Keyword detection (urgent, invoice, sales, etc.)
- Create Needs_Action/X_*.md files for AI processing
- Infinite loop with configurable poll interval
- Logs to Logs/x_watcher.log

Usage:
    python x_watcher.py

Session Management:
    First run: Login manually in the browser window
    Subsequent runs: Session is reused from ./x_session
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
X_URL = "https://twitter.com"
SESSION_DIR = PROJECT_ROOT / "x_session"
POLL_INTERVAL = 60  # seconds
KEYWORDS = ["urgent", "invoice", "sales", "payment", "order", "customer", "complaint", "review", "help", "support"]
NEEDS_ACTION_DIR = PROJECT_ROOT / "Needs_Action"
LOG_DIR = PROJECT_ROOT / "Logs"

# Ensure directories exist
SESSION_DIR.mkdir(exist_ok=True)
NEEDS_ACTION_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "x_watcher.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class XWatcher:
    """Monitor X (Twitter) for mentions and DMs."""

    def __init__(self):
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.processed_items: set = set()

    async def start(self):
        """Start the X watcher."""
        logger.info("Starting X (Twitter) Watcher...")
        logger.info(f"Session directory: {SESSION_DIR}")
        logger.info(f"Monitoring keywords: {KEYWORDS}")
        logger.info(f"Poll interval: {POLL_INTERVAL}s")

        async with async_playwright() as p:
            # Launch browser with persistent context
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=False,  # Show browser for manual login if needed
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )

            # Get the first page or create new one
            if browser.pages:
                self.page = browser.pages[0]
            else:
                self.page = await browser.new_page()

            self.context = browser

            # Navigate to X
            logger.info("Navigating to X (Twitter)...")
            await self.page.goto(X_URL, wait_until='networkidle', timeout=60000)

            # Wait for page to load
            await asyncio.sleep(5)

            # Check if logged in
            is_logged_in = await self.check_login_status()
            if not is_logged_in:
                logger.warning("Not logged in. Please login manually in the browser window.")
                logger.info("Waiting up to 2 minutes for manual login...")
                await asyncio.sleep(120)

            logger.info("X (Twitter) Watcher initialized. Starting monitoring loop...")

            # Main monitoring loop
            await self.monitor_loop()

    async def check_login_status(self) -> bool:
        """Check if user is logged in to X."""
        try:
            # Check for common logged-in indicators
            await self.page.wait_for_selector('[data-testid="SideNav"]', timeout=10000)
            return True
        except Exception:
            return False

    async def monitor_loop(self):
        """Main monitoring loop."""
        while True:
            try:
                await self.check_mentions()
                await self.check_dms()
                await self.check_notifications()
                await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(POLL_INTERVAL)

    async def check_mentions(self):
        """Check for new mentions."""
        logger.debug("Checking for new mentions...")

        try:
            # Navigate to notifications (includes mentions)
            await self.page.goto(f"{X_URL}/notifications", wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Wait for notification list to load
            try:
                await self.page.wait_for_selector('[data-testid="notification"]', timeout=10000)
            except Exception:
                logger.debug("No notifications found")
                return

            # Get recent notifications
            notifications = await self.page.query_selector_all('[data-testid="notification"]')

            for i, notif in enumerate(notifications[:15]):  # Check last 15 notifications
                try:
                    # Check if it's a mention
                    notif_text = await notif.inner_text()
                    if 'mentioned' not in notif_text.lower() and 'replied' not in notif_text.lower():
                        continue

                    # Extract mention data
                    text_elem = await notif.query_selector('[data-testid="tweetText"]')
                    if not text_elem:
                        continue

                    text = await text_elem.inner_text()
                    if not text or len(text) < 2:
                        continue

                    # Get username
                    user_elem = await notif.query_selector('[data-testid="User-Name"]')
                    username = await user_elem.inner_text() if user_elem else "Unknown"

                    # Create unique ID
                    mention_id = f"mention_{i}_{hash(text)}"

                    if mention_id in self.processed_items:
                        continue

                    # Check for keywords
                    matched_keywords = self.check_keywords(text)
                    if matched_keywords:
                        logger.info(f"Mention with keywords found: {matched_keywords}")
                        await self.create_action_file(
                            action_type="mention",
                            content=text,
                            username=username,
                            keywords=matched_keywords,
                            source="X (Twitter) Mentions"
                        )

                    self.processed_items.add(mention_id)

                    # Keep processed items set bounded
                    if len(self.processed_items) > 1000:
                        self.processed_items = set(list(self.processed_items)[-500:])

                except Exception as e:
                    logger.debug(f"Error processing mention: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking mentions: {e}")

    async def check_dms(self):
        """Check for new DMs."""
        logger.debug("Checking for new DMs...")

        try:
            # Navigate to DMs
            await self.page.goto(f"{X_URL}/messages", wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Wait for message list to load
            try:
                await self.page.wait_for_selector('[data-testid="messageConversation"]', timeout=10000)
            except Exception:
                logger.debug("No messages found")
                return

            # Get recent conversations
            conversations = await self.page.query_selector_all('[data-testid="messageConversation"]')

            for i, conv in enumerate(conversations[:10]):  # Check last 10 conversations
                try:
                    # Extract conversation data
                    text_elem = await conv.query_selector('span[dir="auto"]')
                    if not text_elem:
                        continue

                    text = await text_elem.inner_text()
                    if not text or len(text) < 2:
                        continue

                    # Get username
                    user_elem = await conv.query_selector('[data-testid="User-Name"]')
                    username = await user_elem.inner_text() if user_elem else "Unknown"

                    # Create unique ID
                    conv_id = f"dm_{i}_{hash(text)}"

                    if conv_id in self.processed_items:
                        continue

                    # Check for keywords
                    matched_keywords = self.check_keywords(text)
                    if matched_keywords:
                        logger.info(f"DM with keywords found: {matched_keywords}")
                        await self.create_action_file(
                            action_type="dm",
                            content=text,
                            username=username,
                            keywords=matched_keywords,
                            source="X (Twitter) Direct Messages"
                        )

                    self.processed_items.add(conv_id)

                    # Keep processed items set bounded
                    if len(self.processed_items) > 1000:
                        self.processed_items = set(list(self.processed_items)[-500:])

                except Exception as e:
                    logger.debug(f"Error processing DM: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking DMs: {e}")

    async def check_notifications(self):
        """Check for other notifications (likes, retweets, follows)."""
        logger.debug("Checking for new notifications...")

        try:
            # Navigate to notifications
            await self.page.goto(f"{X_URL}/notifications", wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Wait for notification list to load
            try:
                await self.page.wait_for_selector('[data-testid="notification"]', timeout=10000)
            except Exception:
                logger.debug("No notifications found")
                return

            # Get recent notifications
            notifications = await self.page.query_selector_all('[data-testid="notification"]')

            for i, notif in enumerate(notifications[:10]):  # Check last 10 notifications
                try:
                    # Extract notification text
                    text_elem = await notif.query_selector('[data-testid="notificationText"]')
                    if not text_elem:
                        continue

                    text = await text_elem.inner_text()
                    if not text or len(text) < 2:
                        continue

                    # Skip if already processed as mention
                    if 'mentioned' in text.lower() or 'replied' in text.lower():
                        continue

                    # Create unique ID
                    notif_id = f"notif_{i}_{hash(text)}"

                    if notif_id in self.processed_items:
                        continue

                    # Check for keywords in notification
                    matched_keywords = self.check_keywords(text)
                    if matched_keywords:
                        logger.info(f"Notification with keywords found: {matched_keywords}")
                        await self.create_action_file(
                            action_type="notification",
                            content=text,
                            keywords=matched_keywords,
                            source="X (Twitter) Notifications"
                        )

                    self.processed_items.add(notif_id)

                    # Keep processed items set bounded
                    if len(self.processed_items) > 1000:
                        self.processed_items = set(list(self.processed_items)[-500:])

                except Exception as e:
                    logger.debug(f"Error processing notification: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking notifications: {e}")

    def check_keywords(self, text: str) -> List[str]:
        """Check if text contains any monitored keywords."""
        if not text:
            return []

        text_lower = text.lower()
        matched = [kw for kw in KEYWORDS if kw.lower() in text_lower]
        return matched

    async def create_action_file(self, action_type: str, content: str, keywords: List[str],
                                  username: str = None, source: str = ""):
        """Create a Needs_Action file for AI processing."""
        try:
            # Generate filename
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"X_{action_type.upper()}_{timestamp_str}.md"
            filepath = NEEDS_ACTION_DIR / filename

            # Create content
            md_content = f"""# X (Twitter) {action_type.title()} - Needs Action

**Source:** {source}
**Detected:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Username:** @{username}
**Keywords:** {', '.join(keywords)}
**Priority:** {'High' if 'urgent' in keywords else 'Medium'}

---

## Content

```
{content}
```

---

## Suggested Actions

- [ ] Review the {action_type}
- [ ] Determine if response is needed
- [ ] Draft appropriate response (remember X character limit: 280 chars)
- [ ] Take necessary action (support, sales, etc.)

---

## AI Processing

<!-- AI agent will process this file and suggest actions -->
<!-- Move to Pending_Approval/ when action is determined -->
<!-- Move to Approved/ after action is taken -->

## Response Guidelines for X

- Keep responses under 280 characters
- Use professional tone
- Include relevant hashtags if appropriate
- Consider threading for longer responses
"""

            # Write file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)

            logger.info(f"Created action file: {filename}")

        except Exception as e:
            logger.error(f"Error creating action file: {e}")


async def main():
    """Main entry point."""
    watcher = XWatcher()
    try:
        await watcher.start()
    except KeyboardInterrupt:
        logger.info("X (Twitter) Watcher stopped by user")
    except Exception as e:
        logger.error(f"X (Twitter) Watcher error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
