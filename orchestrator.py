#!/usr/bin/env python3
"""
Orchestrator - Central Brain Connector for AI Employee System (Gold Tier)
=========================================================================
Monitors Needs_Action/ directory and processes tasks using AI assistance.
Now includes support for Facebook, Instagram, and X (Twitter) integration.

Usage:
    python orchestrator.py                    # Normal operation mode
    python orchestrator.py --mode=daily-briefing  # Generate weekly briefing

Environment Variables:
    OPENAI_API_BASE     - API endpoint for direct AI calls (optional)
    OPENAI_API_KEY      - API key for direct AI calls (optional)
    DRY_RUN             - If 'true', only print prompts without processing
"""

import os
import sys
import shutil
import time
import logging
import hashlib
import argparse
import re
import subprocess
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# ============================================================================
# Configuration
# ============================================================================

LOGS_DIR = "./Logs"
NEEDS_ACTION_DIR = "./Needs_Action"
DONE_DIR = "./Done"
PLANS_DIR = "./Plans"
PENDING_APPROVAL_DIR = "./Pending_Approval"
APPROVED_DIR = "./Approved"
BRIEFINGS_DIR = "./Briefings"
DASHBOARD_FILE = "./Dashboard.md"
COMPANY_HANDBOOK_FILE = "./Company_Handbook.md"
BUSINESS_GOALS_FILE = "./Business_Goals.md"

# MCP Server Configuration
MCP_SERVERS = {
    'email': {'host': 'localhost', 'port': 8000, 'url': 'http://localhost:8000/rpc'},
    'social': {'host': 'localhost', 'port': 8001, 'url': 'http://localhost:8001/rpc'},
    'browser': {'host': 'localhost', 'port': 8002, 'url': 'http://localhost:8002/rpc'},
    'odoo': {'host': 'localhost', 'port': 8070, 'url': 'http://localhost:8070/rpc'},
}

# Ensure directories exist
for directory in [LOGS_DIR, NEEDS_ACTION_DIR, DONE_DIR, PLANS_DIR, PENDING_APPROVAL_DIR, 
                  APPROVED_DIR, BRIEFINGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'orchestrator.log'), encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Environment configuration
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Auto-execute mode - if true, will call AI API and execute actions
AUTO_EXECUTE = os.getenv("AUTO_EXECUTE", "false").lower() == "true"


# ============================================================================
# AI API Integration - Call OpenAI-compatible APIs
# ============================================================================

def call_ai_api(prompt: str, system_prompt: str = None) -> str:
    """
    Call OpenAI-compatible API to process a prompt.
    
    Args:
        prompt: The user prompt
        system_prompt: Optional system instructions
    
    Returns:
        AI response text or empty string on failure
    """
    if not OPENAI_API_KEY:
        logging.warning("OPENAI_API_KEY not set - cannot call AI API")
        return ""
    
    api_base = OPENAI_API_BASE.rstrip('/') if OPENAI_API_BASE else "https://api.openai.com/v1"
    url = f"{api_base}/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    request = {
        "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
        "messages": messages,
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "2000")),
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    }
    
    try:
        logging.info(f"Calling AI API at {url}")
        data = json.dumps(request).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {OPENAI_API_KEY}'
            }
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            logging.info(f"AI API response received ({len(content)} chars)")
            return content
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        logging.error(f"AI API HTTP error {e.code}: {error_body}")
        return ""
    except Exception as e:
        logging.error(f"AI API error: {e}")
        return ""


# ============================================================================
# System Prompt Template
# ============================================================================

SYSTEM_INSTRUCTIONS = """
You are an autonomous AI Employee working for this organization.

## Your Role
- Process tasks assigned to you in a professional and concise manner
- Think step-by-step before taking action
- Follow all company rules and guidelines

## Company Rules (from Company_Handbook.md)
- Tone: Professional and Concise
- Safety: Never take financial action without approval
- Task Handling: All tasks must move from /Needs_Action → /Done when complete

## Your Workflow

1. **Analyze the Task**: Read the task file content carefully

2. **Plan if Needed**: For multi-step tasks, create a plan file:
   - Location: `Plans/Plan_YYYYMMDD_HHMMSS_<task_name>.md`
   - Include: Objectives, Steps, Resources needed, Expected outcome

3. **Handle Dangerous Actions**: For actions requiring human approval:
   - Create: `Pending_Approval/APPROVAL_<hash>.md`
   - Include: action_type, description, risk_level, instructions

4. **Execute Safely**:
   - Do NOT make financial transactions without approval
   - Do NOT delete important files without confirmation
   - Do NOT send external communications without approval

5. **Complete the Task**:
   - Move original task file from `Needs_Action/` to `Done/`
   - Update `Dashboard.md` with completion entry
   - Write `<TASK_COMPLETE>` at the end of your response

## Output Format
- Be professional and concise
- Use markdown formatting
- Include clear action items
- Log all decisions and reasoning
"""


def build_social_media_prompt(task_file: str, task_content: str, platform: str) -> str:
    """
    Build a specialized prompt for social media task processing.
    
    Handles:
    - FB_*.md files (Facebook messages/notifications)
    - IG_*.md files (Instagram DMs/notifications)
    - X_*.md files (Twitter/X mentions/DMs)
    
    Args:
        task_file: Name of the task file
        task_content: Content of the task file
        platform: Platform identifier (facebook, instagram, x)
    
    Returns:
        Complete formatted prompt string for social media processing
    """
    prompt = f"""
================================================================================
SOCIAL MEDIA TASK PROCESSING PROMPT - {platform.upper()}
================================================================================

You are an autonomous AI Employee. Your task is to process a social media notification.

## Platform: {platform.title()}
## Task Type: Social Media Alert (Message/Notification/Post)

================================================================================
TASK DETAILS
================================================================================

**Task File:** {task_file}
**Received:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Platform:** {platform.title()}

================================================================================
TASK CONTENT
================================================================================

{task_content}

================================================================================
YOUR TASK - STEP BY STEP
================================================================================

## Step 1: Analyze the Social Media Content
- Identify the type (message, notification, comment, mention)
- Determine urgency and priority
- Identify keywords and intent

## Step 2: Classify the Content
Classify into ONE category:
- **customer_inquiry**: Question about products/services
- **support_request**: Technical issue or help needed
- **sales_lead**: Potential business opportunity
- **complaint**: Negative feedback or issue
- **positive_feedback**: Praise or testimonial
- **spam**: Promotional or irrelevant content
- **collaboration**: Partnership or influencer request
- **general**: Everything else

## Step 3: Create a Plan File
Create: `Plans/Plan_SOCIAL_{{short_description}}.md`

Include:
- Content classification
- Key points
- Recommended response strategy
- Timeline for response

## Step 4: Determine if Response is Needed
If response needed:
- Create: `Pending_Approval/SOCIAL_REPLY_{{YYYYMMDD_HHMM}}.md`
- Include frontmatter:
  ```
  ---
  type: social_media_reply
  platform: {platform}
  classification: [your classification]
  priority: high/medium/low
  ---
  ```
- Draft a professional response appropriate for the platform
- Keep it concise and on-brand

## Step 5: Generate Social Post (if action is to post)
If the task requires creating a new post:
- Use the generate_social_post skill
- Specify platform, content, and any media
- Move to Approved/ after generation

## Step 6: Complete Processing
- Move original file from Needs_Action/ to Done/
- Update Dashboard.md
- Write <TASK_COMPLETE> at the end

================================================================================
OUTPUT FORMAT
================================================================================

Structure your response:

### Analysis
[Your analysis of the social media content]

### Classification
[Your classification with reasoning]

### Plan File Content
```markdown
[Content for Plans/Plan_SOCIAL_*.md]
```

### Response Needed?
[Yes/No with reasoning]

### Draft Response (if needed)
```markdown
[Content for Pending_Approval/SOCIAL_REPLY_*.md]
```

### Actions Taken
- [ ] Created plan file
- [ ] Created response draft (if applicable)
- [ ] Moved file to Done/
- [ ] Updated Dashboard.md

<TASK_COMPLETE>

================================================================================
BEGIN YOUR RESPONSE
================================================================================
"""
    return prompt


def build_full_prompt(task_file: str, task_content: str, handbook_content: str = "") -> str:
    """
    Build the complete prompt string for AI processing.
    Detects task type and uses appropriate specialized prompt.
    """
    # Check if this is a social media task (support multiple naming conventions)
    if task_file.startswith("FB_") or task_file.startswith("Facebook_"):
        return build_social_media_prompt(task_file, task_content, "facebook")
    elif task_file.startswith("IG_") or task_file.startswith("Instagram_"):
        return build_social_media_prompt(task_file, task_content, "instagram")
    elif task_file.startswith("X_") or task_file.startswith("Twitter_"):
        return build_social_media_prompt(task_file, task_content, "x")
    
    # Check if this is an email task
    if task_content.strip().startswith('---') and 'type: email' in task_content:
        email_data = parse_email_frontmatter(task_content)
        if email_data:
            return build_email_classification_prompt(task_file, task_content, email_data)
    
    # Use default prompt
    if handbook_content:
        company_rules = handbook_content
    else:
        company_rules = SYSTEM_INSTRUCTIONS

    prompt = f"""
================================================================================
AI EMPLOYEE TASK PROCESSING PROMPT
================================================================================

{SYSTEM_INSTRUCTIONS}

================================================================================
CURRENT TASK
================================================================================

**Task File:** {task_file}
**Received:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Task Content:**
```
{task_content}
```

================================================================================
INSTRUCTIONS
================================================================================

1. Read the task content above carefully
2. Think step-by-step about how to accomplish this task
3. If multi-step, create Plan_*.md in Plans/ directory
4. If action requires approval, create Pending_Approval/*.md
5. When finished:
   - Move original file to Done/
   - Append completion line to Dashboard.md
   - Write <TASK_COMPLETE> at the end of your response

================================================================================
BEGIN YOUR RESPONSE
================================================================================
"""
    return prompt


def parse_email_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from email task content."""
    try:
        match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not match:
            return None
        frontmatter = match.group(1)
        email_data = {}
        for line in frontmatter.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                email_data[key.strip()] = value.strip()
        return email_data
    except Exception as e:
        logging.warning(f"Failed to parse email frontmatter: {e}")
        return None


# ============================================================================
# Dashboard Management
# ============================================================================

def update_dashboard(processed_file_names: list, processed_count: int):
    """Update Dashboard.md with processing results."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    pending_count = 0
    if os.path.exists(NEEDS_ACTION_DIR):
        pending_count = len([f for f in os.listdir(NEEDS_ACTION_DIR)
                            if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))
                            and not f.endswith('_metadata.md')])
    
    if os.path.exists(DASHBOARD_FILE):
        with open(DASHBOARD_FILE, "r") as f:
            lines = f.readlines()
    else:
        lines = ["# Dashboard\n", "\n", "## System Status\n", "System operational\n"]
    
    new_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        
        if "## Pending Tasks Count" in line:
            new_lines.append(line)
            new_lines.append(f"{pending_count}\n")
            skip_next = True
        elif "## Completed Tasks Count" in line:
            new_lines.append(line)
            current = 0
            if i + 1 < len(lines) and re.match(r'^\d+$', lines[i+1].strip()):
                current = int(lines[i+1].strip())
            new_lines.append(f"{current + processed_count}\n")
            skip_next = True
        elif "## Last Processed" in line:
            new_lines.append(line)
            new_lines.append(f"{now}\n")
            skip_next = True
        elif "## Recent Activity" in line:
            new_lines.append(line)
            for name in processed_file_names:
                new_lines.append(f"- {now}: Processed '{name}'\n")
            break
        else:
            new_lines.append(line)
    
    with open(DASHBOARD_FILE, "w") as f:
        f.write("".join(new_lines))
    
    logging.info(f"Dashboard updated: {pending_count} pending, {processed_count} completed")


# ============================================================================
# MCP Client - Call MCP Servers
# ============================================================================

def call_mcp_server(server_name: str, method: str, params: Dict = None, timeout: int = 60) -> Dict:
    """
    Call an MCP server via JSON-RPC.
    
    Args:
        server_name: Name of the MCP server ('email', 'social', 'browser', 'odoo')
        method: RPC method to call
        params: Method parameters
        timeout: Request timeout in seconds
    
    Returns:
        Dict with result or error
    """
    if server_name not in MCP_SERVERS:
        return {'success': False, 'error': f'Unknown MCP server: {server_name}'}
    
    server = MCP_SERVERS[server_name]
    url = server['url']
    
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1
    }
    
    try:
        logging.info(f"Calling MCP {server_name}: {method}")
        logging.debug(f"Request: {json.dumps(request)}")
        
        data = json.dumps(request).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            logging.debug(f"Response: {json.dumps(result)}")
            
            if 'error' in result:
                return {
                    'success': False,
                    'error': result['error'].get('message', 'Unknown error'),
                    'server': server_name
                }
            
            return {
                'success': True,
                'result': result.get('result', {}),
                'server': server_name
            }
            
    except urllib.error.URLError as e:
        logging.error(f"MCP {server_name} connection error: {e}")
        return {
            'success': False,
            'error': f'Connection error: {str(e)}',
            'server': server_name,
            'server_offline': True
        }
    except Exception as e:
        logging.error(f"MCP {server_name} error: {e}")
        return {
            'success': False,
            'error': str(e),
            'server': server_name
        }


def check_mcp_servers() -> Dict:
    """
    Check health of all MCP servers.
    
    Returns:
        Dict with server health status
    """
    health_status = {}
    
    for server_name, server_info in MCP_SERVERS.items():
        result = call_mcp_server(server_name, 'health_check', {})
        health_status[server_name] = {
            'online': result.get('success', False),
            'details': result.get('result', result.get('error', 'Unknown'))
        }
    
    return health_status


# ============================================================================
# MCP Action Handlers - Execute approved actions via MCP
# ============================================================================

def execute_email_action(action_type: str, params: Dict) -> Dict:
    """
    Execute an email action via Email MCP.
    
    Args:
        action_type: Type of action ('send', 'draft', 'reply')
        params: Action parameters
    
    Returns:
        Dict with execution result
    """
    method_map = {
        'send': 'send_email',
        'draft': 'create_draft',
        'reply': 'send_reply',
    }
    
    method = method_map.get(action_type)
    if not method:
        return {'success': False, 'error': f'Unknown email action: {action_type}'}
    
    return call_mcp_server('email', method, params)


def execute_social_action(platform: str, content: str, image_path: str = None) -> Dict:
    """
    Execute a social media post via Social MCP.
    
    Args:
        platform: Platform name ('linkedin', 'facebook', 'instagram', 'x')
        content: Post content
        image_path: Optional image path
    
    Returns:
        Dict with execution result
    """
    method_map = {
        'linkedin': 'post_linkedin',
        'facebook': 'post_facebook',
        'instagram': 'post_instagram',
        'x': 'post_x',
        'twitter': 'post_x',
    }
    
    method = method_map.get(platform.lower())
    if not method:
        return {'success': False, 'error': f'Unknown platform: {platform}'}
    
    params = {'text': content}
    if image_path:
        params['image_path'] = image_path
    
    return call_mcp_server('social', method, params)


def execute_browser_action(action_type: str, params: Dict) -> Dict:
    """
    Execute a browser action via Browser MCP.
    
    Args:
        action_type: Type of action ('navigate', 'fill', 'click', 'screenshot', 'payment')
        params: Action parameters
    
    Returns:
        Dict with execution result
    """
    method_map = {
        'navigate': 'navigate',
        'fill': 'fill',
        'click': 'click',
        'screenshot': 'screenshot',
        'payment': 'process_payment',
        'fill_payment': 'fill_payment',
    }
    
    method = method_map.get(action_type)
    if not method:
        return {'success': False, 'error': f'Unknown browser action: {action_type}'}
    
    return call_mcp_server('browser', method, params)


def execute_odoo_action(action_type: str, params: Dict) -> Dict:
    """
    Execute an Odoo action via Odoo MCP.
    
    Args:
        action_type: Type of action ('create_invoice', 'get_transactions', 'register_payment')
        params: Action parameters
    
    Returns:
        Dict with execution result
    """
    method_map = {
        'create_invoice': 'create_invoice',
        'get_transactions': 'get_transactions',
        'register_payment': 'register_payment',
        'search_partner': 'search_partner',
    }
    
    method = method_map.get(action_type)
    if not method:
        return {'success': False, 'error': f'Unknown Odoo action: {action_type}'}
    
    return call_mcp_server('odoo', method, params)


# ============================================================================
# Social Media Integration
# ============================================================================

def generate_social_post(platform: str, content: str, image_path: str = None) -> bool:
    """
    Generate a social media post using the appropriate poster script.
    
    Args:
        platform: Platform name (facebook, instagram, x)
        content: Post content
        image_path: Optional path to image file
    
    Returns:
        True if successful
    """
    try:
        # Use specific poster for X
        if platform.lower() == 'x':
            cmd = [sys.executable, "x_poster.py", "--text", content]
        else:
            cmd = [sys.executable, "social_poster.py", 
                   "--platform", platform, 
                   "--text", content]
        
        if image_path and os.path.exists(image_path):
            cmd.extend(["--image", image_path])
        
        logging.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            logging.info(f"Social post generated successfully for {platform}")
            return True
        else:
            logging.error(f"Social post failed: {result.stderr}")
            logging.error(f"Stdout: {result.stdout}")
            print(f"\n⚠️  Post failed - check logs for details")
            print(f"Error: {result.stderr[:500] if result.stderr else 'Unknown error'}")
            return False
            
    except Exception as e:
        logging.error(f"Error generating social post: {e}")
        print(f"\n⚠️  Error executing post: {e}")
        return False


def process_approved_file(file_path: str) -> bool:
    """
    Process files moved to Approved/ directory.
    Executes the approved action (e.g., post to social media).
    """
    filename = os.path.basename(file_path)
    
    try:
        with open(file_path, "r", encoding='utf-8') as f:
            content = f.read()
        
        # Check for social media post approval
        if 'type: social_media_post' in content:
            # Extract platform and content from frontmatter
            platform_match = re.search(r'platform:\s*(\w+)', content)
            content_match = re.search(r'post_content:\s*(.+?)(?:\n|$)', content)
            
            if platform_match and content_match:
                platform = platform_match.group(1)
                post_content = content_match.group(1).strip()
                
                logging.info(f"Executing approved social media post for {platform}")
                success = generate_social_post(platform, post_content)
                
                if success:
                    # Move to Done
                    done_path = os.path.join(DONE_DIR, filename)
                    shutil.move(file_path, done_path)
                    logging.info(f"Social post executed and moved to Done")
                    return True
        
        return False
        
    except Exception as e:
        logging.error(f"Error processing approved file: {e}")
        return False


# ============================================================================
# Task Processing
# ============================================================================

def process_task_file(file_path: str, handbook_content: str = "") -> bool:
    """Process a single task file from Needs_Action/."""
    filename = os.path.basename(file_path)
    
    logging.info(f"Processing task: {filename}")
    
    try:
        # Try reading with different encodings to handle BOM
        content = ""
        for encoding in ['utf-8-sig', 'utf-8', 'latin-1']:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        # Strip BOM and null characters if present
        content = content.replace('\ufeff', '').replace('\x00', '').strip()
        
        if not content:
            logging.warning(f"Skipping empty file: {filename}")
            return False
        
        # Check if this is an X (Twitter) post task
        is_x_task = filename.startswith("X_") or filename.startswith("x_") or filename.startswith("Twitter_")

        # Build prompt (support multiple naming conventions)
        if filename.startswith("FB_") or filename.startswith("Facebook_"):
            full_prompt = build_social_media_prompt(filename, content, "facebook")
        elif filename.startswith("IG_") or filename.startswith("Instagram_"):
            full_prompt = build_social_media_prompt(filename, content, "instagram")
        elif is_x_task:
            full_prompt = build_social_media_prompt(filename, content, "x")
        else:
            full_prompt = build_full_prompt(filename, content, handbook_content)
        
        # Print prompt
        logging.info("=" * 80)
        logging.info("FULL PROMPT FOR AI PROCESSING:")
        logging.info("=" * 80)
        print("\n" + full_prompt)
        logging.info("=" * 80)
        
        # Call AI API if configured
        ai_response = ""
        if OPENAI_API_KEY:
            logging.info("Calling AI API to process task...")
            ai_response = call_ai_api(full_prompt, SYSTEM_INSTRUCTIONS)
            if ai_response:
                logging.info("AI Response received:")
                print("\n" + "=" * 80)
                print("AI RESPONSE:")
                print("=" * 80)
                print(ai_response)
                print("=" * 80)
                
                # Save AI response to log
                log_date = datetime.now().strftime("%Y-%m-%d")
                log_path = os.path.join(LOGS_DIR, f"{log_date}_response.md")
                with open(log_path, "a", encoding='utf-8') as log_file:
                    log_file.write(f"\n## {datetime.now().strftime('%H:%M:%S')} - {filename}\n")
                    log_file.write(f"**AI Response:**\n{ai_response}\n")
                    log_file.write("---\n")
            else:
                logging.warning("AI API returned empty response")
        else:
            logging.info("OPENAI_API_KEY not set - prompt displayed but not processed by AI")
        
        # For X_ tasks: Auto-generate and post if no AI response
        post_executed = False
        if is_x_task and not ai_response:
            # Generate a simple post based on the task content
            logging.info("Auto-generating X post content...")
            
            # Extract keywords from task content
            task_lower = content.lower()
            if "ai" in task_lower:
                post_text = "🚀 AI is revolutionizing how we work, create, and solve problems. From automating routine tasks to unlocking new possibilities, the future is here! #AI #Innovation #Technology #FutureOfWork"
            elif "product" in task_lower:
                post_text = "✨ Excited to share our latest product updates! We've been working hard to bring you features that matter. Stay tuned for more! #ProductLaunch #Innovation #Tech"
            elif "news" in task_lower or "update" in task_lower:
                post_text = "📰 Latest updates from our team! We're making great progress on exciting new features. Follow along for more news! #Updates #Tech #Innovation"
            else:
                post_text = f"📝 {content.strip()} #Update #News"
            
            logging.info(f"Generated post: {post_text}")
            
            # Execute the post
            logging.info("Executing X post...")
            post_executed = generate_social_post("x", post_text)
            
            if post_executed:
                print(f"\n✅ X Post executed successfully!")
                print(f"Content: {post_text}")
        
        # Log to daily log
        log_date = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(LOGS_DIR, f"{log_date}.md")
        with open(log_path, "a", encoding='utf-8') as log_file:
            log_file.write(f"\n## {datetime.now().strftime('%H:%M:%S')} - {filename}\n")
            log_file.write(f"**Prompt Length:** {len(full_prompt)} chars\n")
            log_file.write(f"**AI Response:** {'Yes' if ai_response else 'No (no API key)'}\n")
            log_file.write(f"**Post Executed:** {'Yes' if post_executed else 'No'}\n")
            log_file.write(f"**Status:** {'Processed' if ai_response or post_executed else 'Prompt only'}\n")
            log_file.write("---\n")
        
        # Move to Done
        done_path = os.path.join(DONE_DIR, filename)
        shutil.copy2(file_path, done_path)
        os.remove(file_path)
        
        # Update dashboard
        update_dashboard([filename], 1)
        
        logging.info(f"Task completed: {filename}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to process {filename}: {e}")
        return False


class NeedsActionHandler(FileSystemEventHandler):
    """Watches Needs_Action/ for new files including FB/IG/X files."""
    
    def __init__(self, handbook_content: str = ""):
        self.handbook_content = handbook_content
        self.processing_lock = False
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Skip metadata and hidden files
        if filename.endswith('_metadata.md') or filename.startswith('.'):
            return
        
        logging.info(f"New task detected: {filename}")
        time.sleep(0.5)
        
        if self.processing_lock:
            logging.info(f"Processor busy, will retry {filename}")
            return
        
        try:
            self.processing_lock = True
            process_task_file(file_path, self.handbook_content)
        finally:
            self.processing_lock = False


def process_all_pending():
    """Process all files in Needs_Action/."""
    if not os.path.exists(NEEDS_ACTION_DIR):
        logging.info("Needs_Action directory does not exist")
        return
    
    handbook_content = ""
    if os.path.exists(COMPANY_HANDBOOK_FILE):
        with open(COMPANY_HANDBOOK_FILE, "r", encoding='utf-8') as f:
            handbook_content = f.read()
    
    files = [f for f in os.listdir(NEEDS_ACTION_DIR) 
             if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f)) 
             and not f.endswith('_metadata.md')]
    
    logging.info(f"Found {len(files)} files to process")
    
    for filename in files:
        file_path = os.path.join(NEEDS_ACTION_DIR, filename)
        process_task_file(file_path, handbook_content)
        time.sleep(1)


def process_approved_pending():
    """Process files in Approved/ that need execution."""
    if not os.path.exists(APPROVED_DIR):
        return
    
    files = [f for f in os.listdir(APPROVED_DIR)
             if os.path.isfile(os.path.join(APPROVED_DIR, f))]
    
    for filename in files:
        file_path = os.path.join(APPROVED_DIR, filename)
        logging.info(f"Processing approved file: {filename}")
        process_approved_file(file_path)


def run_weekly_audit_mode():
    """Run weekly audit mode - generate CEO briefing."""
    logging.info("=" * 60)
    logging.info("WEEKLY AUDIT MODE - Generating CEO Briefing")
    logging.info("=" * 60)
    
    try:
        # Import weekly_audit module
        import weekly_audit
        
        # Run the audit
        briefing_path = weekly_audit.run_weekly_audit()
        
        if briefing_path:
            logging.info(f"Weekly audit complete: {briefing_path}")
        else:
            logging.error("Weekly audit failed to generate briefing")
            
    except ImportError as e:
        logging.error(f"Failed to import weekly_audit module: {e}")
        logging.error("Ensure weekly_audit.py is in the same directory")
    except Exception as e:
        logging.error(f"Weekly audit failed: {e}")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='AI Employee Orchestrator')
    parser.add_argument('--mode', choices=['normal', 'daily-briefing', 'weekly-audit', 'loop'], default='normal',
                        help='Operation mode')
    parser.add_argument('--max-iterations', type=int, default=10,
                        help='Max iterations for loop mode (default: 10)')
    args = parser.parse_args()
    
    # Handle loop mode - use Ralph Wiggum controller
    if args.mode == 'loop':
        logging.info("=" * 60)
        logging.info("Starting in RALPH WIGGUM LOOP MODE")
        logging.info(f"Max iterations per task: {args.max_iterations}")
        logging.info("=" * 60)
        
        try:
            import ralph_wiggum
            ralph_wiggum.run_orchestrator_with_loop(max_iterations=args.max_iterations)
        except ImportError:
            logging.error("Failed to import ralph_wiggum module")
            logging.error("Ensure ralph_wiggum.py is in the same directory")
            sys.exit(1)
        return

    # Handle weekly-audit mode (one-time execution)
    if args.mode == 'weekly-audit':
        run_weekly_audit_mode()
        return

    logging.info("=" * 60)
    logging.info("AI EMPLOYEE ORCHESTRATOR (Gold Tier) started")
    logging.info("=" * 60)
    logging.info(f"Monitoring: {NEEDS_ACTION_DIR}")
    logging.info(f"Social platforms: Facebook, Instagram, X")
    logging.info("=" * 60)
    
    # Load handbook
    handbook_content = ""
    if os.path.exists(COMPANY_HANDBOOK_FILE):
        with open(COMPANY_HANDBOOK_FILE, "r", encoding='utf-8') as f:
            handbook_content = f.read()
        logging.info(f"Loaded Company Handbook ({len(handbook_content)} chars)")
    
    # Process any pending approved files
    process_approved_pending()
    
    # Process existing files
    process_all_pending()
    
    # Start watcher
    event_handler = NeedsActionHandler(handbook_content)
    observer = Observer()
    observer.schedule(event_handler, NEEDS_ACTION_DIR, recursive=False)
    observer.start()
    
    logging.info("File watcher started. Waiting for new tasks...")
    logging.info("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(60)
            # Periodically check approved folder
            process_approved_pending()
    except KeyboardInterrupt:
        logging.info("Stopping orchestrator...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
