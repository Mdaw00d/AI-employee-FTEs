#!/usr/bin/env python3
"""
Post Scheduler - Automated Future Post Execution
=================================================
Monitors Scheduled_Posts/ directory and executes posts at their scheduled times.

Usage:
    python post_scheduler.py

Features:
    - Checks every 60 seconds for posts due to publish
    - Supports LinkedIn, Facebook, Instagram, X
    - Automatic retry on failure
    - Logs all activity
"""

import os
import sys
import time
import logging
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Configuration
SCHEDULED_DIR = "./Scheduled_Posts"
APPROVED_DIR = "./Approved"
DONE_DIR = "./Done"
LOGS_DIR = "./Logs"
CHECK_INTERVAL = 60  # seconds
MAX_RETRIES = 3

# Ensure directories exist
for directory in [SCHEDULED_DIR, APPROVED_DIR, DONE_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Setup logging
LOG_FILE = os.path.join(LOGS_DIR, "post_scheduler.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class ScheduledPost:
    """Represents a scheduled social media post."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.platform = ""
        self.scheduled_time: Optional[datetime] = None
        self.execute_after: Optional[datetime] = None
        self.post_content = ""
        self.priority = "medium"
        self.parse_file()
    
    def parse_file(self):
        """Parse the scheduled post file to extract metadata."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract frontmatter
            frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if frontmatter_match:
                frontmatter = frontmatter_match.group(1)
                
                # Parse platform
                platform_match = re.search(r'platform:\s*(\w+)', frontmatter)
                if platform_match:
                    self.platform = platform_match.group(1).lower()
                
                # Parse scheduled time
                scheduled_match = re.search(r'scheduled_time:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)', 
                                          frontmatter, re.IGNORECASE)
                if scheduled_match:
                    time_str = scheduled_match.group(1)
                    try:
                        # Try parsing with AM/PM
                        self.scheduled_time = datetime.strptime(time_str, "%Y-%m-%d %I:%M %p")
                    except ValueError:
                        try:
                            # Try 24-hour format
                            self.scheduled_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                        except ValueError:
                            logger.warning(f"Could not parse scheduled time: {time_str}")
                
                # Parse execute_after time
                execute_match = re.search(r'execute_after:\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)', 
                                        frontmatter, re.IGNORECASE)
                if execute_match:
                    time_str = execute_match.group(1)
                    try:
                        self.execute_after = datetime.strptime(time_str, "%Y-%m-%d %I:%M %p")
                    except ValueError:
                        try:
                            self.execute_after = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                        except ValueError:
                            logger.warning(f"Could not parse execute_after time: {time_str}")
                
                # Parse priority
                priority_match = re.search(r'priority:\s*(\w+)', frontmatter)
                if priority_match:
                    self.priority = priority_match.group(1).lower()

                # Extract post content - handle both inline and multiline formats
                # Find post_content line and capture everything until the next YAML key or end of frontmatter
                lines = frontmatter.split('\n')
                post_content_lines = []
                in_post_content = False
                
                for i, line in enumerate(lines):
                    if line.startswith('post_content:'):
                        # Get content after the colon on the same line
                        after_colon = line.split(':', 1)[1].strip()
                        if after_colon:
                            post_content_lines.append(after_colon)
                        in_post_content = True
                    elif in_post_content:
                        # Check if this is a new YAML key (word at start followed by colon)
                        if re.match(r'^\w+:', line):
                            # New YAML key found, stop collecting
                            break
                        else:
                            # This is a continuation line (including empty lines)
                            post_content_lines.append(line)
                
                if post_content_lines:
                    self.post_content = '\n'.join(post_content_lines).strip()
            
            logger.info(f"Parsed scheduled post: {self.filename}")
            logger.info(f"  Platform: {self.platform}")
            logger.info(f"  Scheduled: {self.scheduled_time}")
            logger.info(f"  Execute after: {self.execute_after}")
            
        except Exception as e:
            logger.error(f"Error parsing {self.filename}: {e}")
    
    def is_due(self) -> bool:
        """Check if this post is due to be executed."""
        now = datetime.now()
        
        # Use execute_after time if available, otherwise use scheduled_time
        target_time = self.execute_after or self.scheduled_time
        
        if not target_time:
            logger.warning(f"No valid time found for {self.filename}")
            return False
        
        # Post is due if we're at or past the execute time
        return now >= target_time
    
    def time_until_due(self) -> timedelta:
        """Get time remaining until post is due."""
        now = datetime.now()
        target_time = self.execute_after or self.scheduled_time
        
        if not target_time:
            return timedelta(0)
        
        return target_time - now
    
    def execute(self) -> bool:
        """Execute the post."""
        logger.info(f"Executing scheduled post: {self.filename}")
        logger.info(f"  Platform: {self.platform}")
        logger.info(f"  Content length: {len(self.post_content)} chars")

        # Map platform to poster script
        # Format: (script_name, use_positional_arg, timeout_seconds, use_async)
        # LinkedIn needs more time due to browser navigation
        platform_scripts = {
            'linkedin': ('linkedin_poster.py', True, 600, True),   # uses positional arg, 10 min timeout, async
            'facebook': ('facebook_poster.py', False, 300, False),  # uses --text, 5 min timeout
            'instagram': ('instagram_poster.py', False, 300, False), # uses --text, 5 min timeout
            'x': ('x_poster.py', False, 300, False),                # uses --text, 5 min timeout
            'twitter': ('x_poster.py', False, 300, False),          # uses --text, 5 min timeout
        }

        platform_info = platform_scripts.get(self.platform)
        if not platform_info:
            logger.error(f"Unknown platform: {self.platform}")
            return False

        script, use_positional, timeout, use_async = platform_info

        # Build command - LinkedIn uses positional arg, others use --text
        # Remove --dry-run to allow actual posting
        if use_positional:
            cmd = [sys.executable, script, self.post_content]
        else:
            cmd = [sys.executable, script, '--text', self.post_content]

        try:
            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            # Log stdout for detailed output from poster scripts
            if result.stdout:
                logger.info(f"Poster output:\n{result.stdout}")
            
            # Log stderr for errors
            if result.stderr:
                logger.error(f"Poster errors:\n{result.stderr}")

            if result.returncode == 0:
                logger.info(f"Post successful: {self.filename}")
                return True
            else:
                logger.error(f"Post failed with exit code {result.returncode}: {self.filename}")
                return False

        except subprocess.TimeoutExpired as e:
            logger.error(f"Post timeout: {self.filename}")
            logger.error(f"Timeout output:\n{e.stdout if e.stdout else 'No output'}")
            logger.error(f"Timeout errors:\n{e.stderr if e.stderr else 'No errors'}")
            return False
        except Exception as e:
            logger.error(f"Post error: {self.filename} - {e}")
            return False
    
    def move_to_done(self):
        """Move post file to Done directory."""
        try:
            done_path = os.path.join(DONE_DIR, self.filename)
            
            # Add timestamp to filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(self.filename)[0]
            ext = os.path.splitext(self.filename)[1]
            new_filename = f"{base_name}_EXECUTED_{timestamp}{ext}"
            done_path = os.path.join(DONE_DIR, new_filename)
            
            # Move file
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add execution metadata
            content += f"\n\n---\n**EXECUTED**\n\n- Executed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n- Platform: {self.platform}\n- Status: ✅ Published\n"
            
            with open(done_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Delete original
            os.remove(self.file_path)
            
            logger.info(f"Moved to Done: {new_filename}")
            
        except Exception as e:
            logger.error(f"Error moving to Done: {e}")
    
    def move_to_approved(self):
        """Move post to Approved directory for immediate execution."""
        try:
            approved_path = os.path.join(APPROVED_DIR, self.filename)
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update content for approved format
            content += f"\n\n**READY FOR EXECUTION**\n\nExecute at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            with open(approved_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            os.remove(self.file_path)
            logger.info(f"Moved to Approved: {self.filename}")
            
        except Exception as e:
            logger.error(f"Error moving to Approved: {e}")


def load_scheduled_posts() -> List[ScheduledPost]:
    """Load all scheduled posts from the Scheduled_Posts directory."""
    posts = []
    
    if not os.path.exists(SCHEDULED_DIR):
        return posts
    
    for filename in os.listdir(SCHEDULED_DIR):
        if filename.endswith('.md'):
            file_path = os.path.join(SCHEDULED_DIR, filename)
            post = ScheduledPost(file_path)
            if post.scheduled_time:
                posts.append(post)
    
    # Sort by priority and time
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    posts.sort(key=lambda p: (priority_order.get(p.priority, 1), p.scheduled_time or datetime.max))
    
    return posts


def main():
    """Main scheduler loop."""
    logger.info("=" * 70)
    logger.info("Post Scheduler starting...")
    logger.info(f"Watching: {SCHEDULED_DIR}/")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
    logger.info("=" * 70)
    
    retry_count = 0
    
    while True:
        try:
            # Load all scheduled posts
            posts = load_scheduled_posts()
            
            if not posts:
                logger.info(f"No scheduled posts found. Checking again in {CHECK_INTERVAL}s...")
            else:
                logger.info(f"Found {len(posts)} scheduled post(s)")
                
                # Check each post
                for post in posts:
                    time_until = post.time_until_due()
                    
                    if time_until.total_seconds() <= 0:
                        # Post is due!
                        logger.info(f"⏰ POST DUE: {post.filename}")
                        logger.info(f"   Scheduled: {post.scheduled_time}")
                        logger.info(f"   Platform: {post.platform}")
                        
                        # Execute the post
                        success = post.execute()
                        
                        if success:
                            post.move_to_done()
                            logger.info(f"✅ POST PUBLISHED: {post.filename}")
                        else:
                            logger.warning(f"⚠️ POST FAILED: {post.filename}")
                            # Could move to a Failed directory for manual review
                    else:
                        # Post not due yet
                        hours, remainder = divmod(int(time_until.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        logger.info(f"   ⏳ {post.filename} in {hours}h {minutes}m {seconds}s")
            
            # Reset retry count
            retry_count = 0
            
            # Wait until next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"Error in scheduler loop (attempt {retry_count}/3): {e}")
            
            if retry_count <= 3:
                backoff = min(60 * (2 ** (retry_count - 1)), 300)
                logger.info(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
            else:
                logger.error("Max retries exceeded")
                retry_count = 0
    
    logger.info("Post Scheduler shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
