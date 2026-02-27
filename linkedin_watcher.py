"""
LinkedIn Watcher - Monitors LinkedIn for messages and connection requests requiring action.

Dependencies:
    pip install playwright

Usage:
    python linkedin_watcher.py

Note: First run requires manual login at LinkedIn.
      Session is persisted in ./linkedin_session for subsequent runs.
"""

import os
import time
import logging
import hashlib
import random
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configure logging
os.makedirs('./Logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./Logs/linkedin_watcher.log'),
        logging.StreamHandler()
    ]
)

# Keywords that indicate a message needs action
ACTION_KEYWORDS = ['lead', 'proposal', 'pricing', 'quote', 'interested', 'buy', 'service', 'freelance']

# High priority keywords (elevates priority from medium to high)
HIGH_PRIORITY_KEYWORDS = ['urgent', 'asap', 'immediately', 'buy', 'pricing', 'proposal']

# Retry configuration
MAX_RETRIES = 5
BASE_BACKOFF = 5  # seconds


def create_needs_action_file(
    sender: str,
    content: str,
    message_type: str,
    priority: str = 'medium',
    link: str = ''
) -> str:
    """
    Creates a task file in Needs_Action directory for LinkedIn items requiring attention.
    
    Args:
        sender: Name of the sender/requester
        content: Message content or connection request note
        message_type: Type of LinkedIn item (message, connection_request, notification)
        priority: Priority level (low, medium, high)
        link: Direct link to the conversation/profile
        
    Returns:
        Path to the created file
    """
    needs_action_dir = './Needs_Action'
    os.makedirs(needs_action_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    sender_hash = hashlib.md5(sender.encode()).hexdigest()[:8]
    filename = f"LINKEDIN_{timestamp}_{sender_hash}.md"
    filepath = os.path.join(needs_action_dir, filename)
    
    # Generate suggested actions based on message type and keywords
    suggested_actions = []
    content_lower = content.lower()
    
    if message_type == 'connection_request':
        suggested_actions.append("- [ ] Review sender profile")
        suggested_actions.append("- [ ] Accept or decline connection request")
        if any(kw in content_lower for kw in ACTION_KEYWORDS):
            suggested_actions.append("- [ ] Respond to message in connection note")
    elif message_type == 'message':
        suggested_actions.append("- [ ] Read full message")
        suggested_actions.append("- [ ] Draft response")
        if any(kw in content_lower for kw in ['lead', 'interested', 'buy']):
            suggested_actions.append("- [ ] Qualify the lead")
            suggested_actions.append("- [ ] Schedule call if appropriate")
        if any(kw in content_lower for kw in ['proposal', 'pricing', 'quote', 'freelance', 'service']):
            suggested_actions.append("- [ ] Prepare proposal/pricing information")
            suggested_actions.append("- [ ] Review scope of work")
    elif message_type == 'notification':
        suggested_actions.append("- [ ] Review notification details")
        suggested_actions.append("- [ ] Take appropriate action")
    
    # Default action if no specific matches
    if not suggested_actions:
        suggested_actions.append("- [ ] Review and respond")
    
    # Priority-based actions
    if priority == 'high':
        suggested_actions.insert(0, "- [ ] **HIGH PRIORITY** - Respond within 2 hours")
    
    suggested_actions_str = '\n'.join(suggested_actions)
    
    file_content = f"""---
source: LinkedIn
type: {message_type}
sender: {sender}
timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
priority: {priority}
status: pending
link: {link}
---

# LinkedIn Item Requiring Action

## From
**Name:** {sender}

## Type
{message_type.replace('_', ' ').title()}

## Content
{content if content else '(No message content)'}

## Suggested Actions
{recommended_actions_str}

## Notes
_Add any additional context or actions below_

"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(file_content)
    
    logging.info(f"Created task file: {filename}")
    return filepath


def wait_for_linkedin_load(page, timeout: int = 30000) -> bool:
    """
    Waits for LinkedIn messaging page to load.
    
    Args:
        page: Playwright page object
        timeout: Maximum wait time in milliseconds
        
    Returns:
        True if page loaded successfully, False otherwise
    """
    try:
        # Wait for messaging container or main feed
        selectors = [
            'div.msg-compose-button',  # Message compose button
            'div.msg-conversations-container',  # Conversations list
            'div.notification-card',  # Notifications
            'ul.msg-conversation-list',  # Conversation list
        ]
        
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=timeout)
                logging.info(f"LinkedIn loaded (detected via: {selector})")
                return True
            except PlaywrightTimeout:
                continue
        
        logging.warning("Could not detect LinkedIn page with standard selectors")
        return False
        
    except Exception as e:
        logging.error(f"Error waiting for LinkedIn load: {e}")
        return False


def check_login_required(page) -> bool:
    """
    Checks if LinkedIn is showing the login page.
    
    Args:
        page: Playwright page object
        
    Returns:
        True if login is required, False if already logged in
    """
    try:
        # Check for login page indicators
        login_selectors = [
            'input[id="session_key"]',  # Login email field
            'button[type="submit"]',  # Login submit button
        ]
        
        for selector in login_selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    return True
            except:
                continue
        
        return False
        
    except Exception as e:
        logging.error(f"Error checking login status: {e}")
        return False


def scan_unread_messages(page) -> list:
    """
    Scans for unread messages in LinkedIn messaging.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of dicts with sender, message, and type
    """
    unread_items = []
    
    try:
        # JavaScript to extract unread messages from LinkedIn
        extract_messages_script = """
        () => {
            const items = [];
            
            // Find conversation list items with unread indicator
            const conversationElements = document.querySelectorAll('div.msg-conversation-card__link, li.msg-conversation-list__item');
            
            conversationElements.forEach((el, index) => {
                // Check for unread indicator (various possible selectors)
                const unreadIndicator = el.querySelector('span.msg-unread-count, .msg-conversation-card__unread-count, [aria-label*="unread"]');
                const hasUnread = unreadIndicator !== null || el.classList.contains('msg-conversation-list__item--unread');
                
                if (hasUnread) {
                    const nameEl = el.querySelector('span.msg-sender__name, h4.msg-conversation-card__sender-name, span.entity-heading__name');
                    const messageEl = el.querySelector('span.msg-message-preview, p.msg-conversation-card__message-preview');
                    
                    if (nameEl) {
                        items.push({
                            type: 'message',
                            sender: nameEl.textContent.trim(),
                            message: messageEl ? messageEl.textContent.trim() : '',
                            priority: 'medium'
                        });
                    }
                }
            });
            
            return items;
        }
        """
        
        items = page.evaluate(extract_messages_script)
        unread_items.extend(items)
        
    except Exception as e:
        logging.error(f"Error scanning messages: {e}")
    
    return unread_items


def scan_connection_requests(page) -> list:
    """
    Scans for pending connection requests.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of dicts with sender name and note
    """
    connection_requests = []
    
    try:
        # JavaScript to extract connection requests
        extract_requests_script = """
        () => {
            const requests = [];
            
            // Look for connection request cards in notifications or invitations
            const requestElements = document.querySelectorAll(
                'div.invitation-card, div.connection-request, [data-control-name="request_item_inbox"]'
            );
            
            requestElements.forEach((el, index) => {
                const nameEl = el.querySelector(
                    'span.entity-heading__name, h3.invitation-card__title, a[href*="/in/"]'
                );
                const noteEl = el.querySelector(
                    'p.invitation-card__message, span.connection-request-note'
                );
                
                if (nameEl) {
                    requests.push({
                        type: 'connection_request',
                        sender: nameEl.textContent.trim(),
                        message: noteEl ? noteEl.textContent.trim() : '',
                        priority: 'medium'
                    });
                }
            });
            
            return requests;
        }
        """
        
        requests = page.evaluate(extract_requests_script)
        connection_requests.extend(requests)
        
    except Exception as e:
        logging.error(f"Error scanning connection requests: {e}")
    
    return connection_requests


def scan_notifications(page) -> list:
    """
    Scans for notifications that may require action.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of dicts with notification details
    """
    notifications = []
    
    try:
        # JavaScript to extract notifications
        extract_notifications_script = """
        () => {
            const notifications = [];
            
            // Look for unread notification cards
            const notificationElements = document.querySelectorAll(
                'div.notification-card.unread, li.notification-item.unread, [data-analytics-name="notification-click"]'
            );
            
            notificationElements.forEach((el) => {
                const contentEl = el.querySelector(
                    'span.notification-content, p.notification-message, div.notification-text'
                );
                const actorEl = el.querySelector(
                    'span.actor-name, img.notification-actor-image[alt]'
                );
                
                if (contentEl) {
                    const content = contentEl.textContent.trim();
                    const actor = actorEl ? actorEl.textContent.trim() || actorEl.getAttribute('alt') : 'Unknown';
                    
                    // Check if notification contains action keywords
                    notifications.push({
                        type: 'notification',
                        sender: actor,
                        message: content,
                        priority: 'low'
                    });
                }
            });
            
            return notifications;
        }
        """
        
        items = page.evaluate(extract_notifications_script)
        notifications.extend(items)
        
    except Exception as e:
        logging.error(f"Error scanning notifications: {e}")
    
    return notifications


def determine_priority(content: str, message_type: str) -> str:
    """
    Determines priority level based on content and type.
    
    Args:
        content: Message/notification content
        message_type: Type of item
        
    Returns:
        Priority string: 'low', 'medium', or 'high'
    """
    content_lower = content.lower()
    
    # High priority keywords
    if any(kw in content_lower for kw in HIGH_PRIORITY_KEYWORDS):
        return 'high'
    
    # Medium priority for business-related keywords
    if any(kw in content_lower for kw in ACTION_KEYWORDS):
        return 'medium'
    
    # Connection requests are medium priority
    if message_type == 'connection_request':
        return 'medium'
    
    # Default to low
    return 'low'


def main():
    """Main LinkedIn watcher loop."""
    logging.info("=" * 60)
    logging.info("LinkedIn Watcher starting...")
    logging.info("Session directory: ./linkedin_session")
    logging.info("Monitoring for keywords: %s", ', '.join(ACTION_KEYWORDS))
    logging.info("High priority keywords: %s", ', '.join(HIGH_PRIORITY_KEYWORDS))
    logging.info("=" * 60)
    
    user_data_dir = os.path.abspath("./linkedin_session")
    os.makedirs(user_data_dir, exist_ok=True)
    
    retry_count = 0
    
    with sync_playwright() as p:
        # Launch browser in headless mode with persistent context
        # Set headless=False for first run to complete login
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # Change to False for first run to login
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--enable-features=NetworkService',
                '--lang=en-US',
            ]
        )
        
        context = browser
        page = context.new_page()
        
        logging.info("Navigating to LinkedIn Messaging...")
        page.goto("https://www.linkedin.com/messaging/", wait_until="networkidle", timeout=60000)
        
        # Check if login is required
        if check_login_required(page):
            logging.warning("Login required. Please log in to LinkedIn manually.")
            logging.warning("Waiting for login completion (max 5 minutes)...")
            
            # Wait for user to log in
            login_timeout = 300  # 5 minutes
            login_start = time.time()
            
            while check_login_required(page) and (time.time() - login_start) < login_timeout:
                time.sleep(5)
            
            if check_login_required(page):
                logging.error("Login timeout. Please restart the script after logging in.")
                browser.close()
                return
            
            logging.info("Login detected. Continuing...")
        
        # Wait for LinkedIn to fully load
        logging.info("Waiting for LinkedIn to load...")
        wait_for_linkedin_load(page, timeout=60000)
        
        logging.info("LinkedIn Watcher is now monitoring...")
        logging.info("Scan interval: 90 seconds")
        logging.info("Monitoring: Messages, Connection Requests, Notifications")
        
        while True:
            try:
                items_found = []
                
                # Scan for unread messages
                logging.debug("Scanning for unread messages...")
                unread_messages = scan_unread_messages(page)
                items_found.extend(unread_messages)
                
                # Scan for connection requests
                logging.debug("Scanning for connection requests...")
                connection_requests = scan_connection_requests(page)
                items_found.extend(connection_requests)
                
                # Scan for notifications
                logging.debug("Scanning for notifications...")
                notifications = scan_notifications(page)
                items_found.extend(notifications)
                
                if items_found:
                    logging.info(f"Found {len(items_found)} item(s) requiring attention")
                    
                    for item in items_found:
                        content = item.get('message', '')
                        content_lower = content.lower()
                        
                        # Check if item contains action keywords
                        has_keywords = any(keyword in content_lower for keyword in ACTION_KEYWORDS)
                        
                        # Always process connection requests, filter messages/notifications by keywords
                        if item['type'] == 'connection_request' or has_keywords:
                            priority = determine_priority(content, item['type'])
                            
                            logging.info(
                                f"Action required - Type: {item['type']}, "
                                f"From: {item['sender']}, "
                                f"Priority: {priority}"
                            )
                            
                            try:
                                create_needs_action_file(
                                    sender=item['sender'],
                                    content=content,
                                    message_type=item['type'],
                                    priority=priority,
                                    link="https://www.linkedin.com/messaging/"
                                )
                            except Exception as e:
                                logging.error(f"Failed to create task file: {e}")
                        else:
                            logging.debug(
                                f"Skipping (no keywords) - From: {item['sender']}"
                            )
                else:
                    logging.debug("No new items found")
                
                # Reset retry count on success
                retry_count = 0
                
            except Exception as e:
                retry_count += 1
                logging.error(f"Error during scan (attempt {retry_count}/{MAX_RETRIES}): {e}")
                
                # Exponential backoff with jitter
                if retry_count <= MAX_RETRIES:
                    backoff_time = min(BASE_BACKOFF * (2 ** (retry_count - 1)), 300)
                    jitter = random.uniform(0, backoff_time * 0.1)
                    total_wait = backoff_time + jitter
                    
                    logging.info(f"Retrying in {total_wait:.1f} seconds...")
                    time.sleep(total_wait)
                    
                    # Try to recover by reloading page
                    try:
                        logging.info("Attempting to recover by reloading LinkedIn...")
                        page.reload(wait_until="networkidle")
                        wait_for_linkedin_load(page, timeout=30000)
                    except Exception as reload_error:
                        logging.error(f"Recovery failed: {reload_error}")
                else:
                    logging.error("Max retries exceeded. Attempting full restart...")
                    retry_count = 0
                    
                    try:
                        browser.close()
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=False,
                            viewport={"width": 1280, "height": 720},
                            args=['--disable-gpu', '--disable-dev-shm-usage']
                        )
                        context = browser
                        page = context.new_page()
                        page.goto("https://www.linkedin.com/messaging/", wait_until="networkidle")
                    except Exception as restart_error:
                        logging.error(f"Restart failed: {restart_error}")
                        time.sleep(60)
            
            # Sleep for 90 seconds
            sleep_time = 90
            logging.debug(f"Next scan in {sleep_time} seconds")
            time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("LinkedIn Watcher stopped by user")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        raise
