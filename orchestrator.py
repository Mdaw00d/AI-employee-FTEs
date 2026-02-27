"""
Orchestrator - Central Brain Connector for AI Employee System

Monitors Needs_Action/ directory and processes tasks using AI assistance.
Generates complete prompts for AI processing with full context.

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
from datetime import datetime, timedelta
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ============================================================================
# Configuration
# ============================================================================

LOGS_DIR = "./Logs"
NEEDS_ACTION_DIR = "./Needs_Action"
DONE_DIR = "./Done"
PLANS_DIR = "./Plans"
PENDING_APPROVAL_DIR = "./Pending_Approval"
BRIEFINGS_DIR = "./Briefings"
DASHBOARD_FILE = "./Dashboard.md"
COMPANY_HANDBOOK_FILE = "./Company_Handbook.md"
BUSINESS_GOALS_FILE = "./Business_Goals.md"

# Ensure directories exist
for directory in [LOGS_DIR, NEEDS_ACTION_DIR, DONE_DIR, PLANS_DIR, PENDING_APPROVAL_DIR, BRIEFINGS_DIR]:
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


def build_email_classification_prompt(task_file: str, task_content: str, email_data: dict) -> str:
    """
    Build a specialized prompt for email classification and processing.
    
    This prompt asks the AI to:
    1. Classify the email (sales/invoice/support/spam/general)
    2. Create a Plan_EMAIL_*.md file
    3. If reply needed, create Pending_Approval/EMAIL_REPLY_*.md with draft text

    Args:
        task_file: Name of the task file
        task_content: Content of the task file
        email_data: Parsed email frontmatter data

    Returns:
        Complete formatted prompt string for email processing
    """
    prompt = f"""
================================================================================
EMAIL PROCESSING PROMPT - AI EMPLOYEE
================================================================================

You are an autonomous AI Employee. Your task is to process an incoming email.

## Your Role
- Classify the email type
- Determine if a reply is needed
- Create appropriate plan and approval files
- Move the task to completion

================================================================================
EMAIL DETAILS
================================================================================

**From:** {email_data.get('from', 'Unknown')}
**To:** {email_data.get('to', '')}
**Subject:** {email_data.get('subject', 'No Subject')}
**Received:** {email_data.get('received', 'Unknown')}
**Priority:** {email_data.get('priority', 'medium')}
**Message ID:** {email_data.get('message_id', 'Unknown')}

================================================================================
EMAIL CONTENT
================================================================================

{task_content}

================================================================================
YOUR TASK - STEP BY STEP
================================================================================

## Step 1: Classify the Email
Classify this email into ONE of these categories:
- **sales**: Inquiry about products/services, pricing requests, lead generation
- **invoice**: Bills, payment requests, receipts, financial documents
- **support**: Technical issues, bug reports, help requests, troubleshooting
- **spam**: Promotional, unsolicited, irrelevant, or suspicious content
- **general**: Everything else (networking, updates, informational, etc.)

## Step 2: Create a Plan File
Create a file in Plans/ directory named: `Plan_EMAIL_{short_description}.md`

Include:
- Email classification
- Key points from the email
- Required actions
- Timeline/deadlines if mentioned

## Step 3: Determine if Reply is Needed
If the email requires a response:
- Create: `Pending_Approval/EMAIL_REPLY_{YYYYMMDD_HHMM}.md`
- Include frontmatter:
  ```
  ---
  type: email_reply_draft
  to: {email_data.get('from', '')}
  subject: Re: {email_data.get('subject', '')}
  original_message_id: {email_data.get('message_id', '')}
  classification: [your classification]
  priority: {email_data.get('priority', 'medium')}
  ---
  ```
- Write a professional draft reply in the body
- Include suggested attachments or follow-ups if needed

If NO reply needed (e.g., spam, FYI emails):
- Note this in the plan file
- Recommend archiving or other action

## Step 4: Complete Processing
- Move original email file from Needs_Action/ to Done/
- Update Dashboard.md
- Write <TASK_COMPLETE> at the end

================================================================================
OUTPUT FORMAT
================================================================================

Structure your response as follows:

### Classification
[Your classification with reasoning]

### Plan File Content
```markdown
[Content for Plans/Plan_EMAIL_*.md]
```

### Reply Needed?
[Yes/No with reasoning]

### Draft Reply (if needed)
```markdown
[Content for Pending_Approval/EMAIL_REPLY_*.md]
```

### Actions Taken
- [ ] Created plan file
- [ ] Created reply draft (if applicable)
- [ ] Moved email to Done/
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

    Args:
        task_file: Name of the task file
        task_content: Content of the task file
        handbook_content: Optional content from Company_Handbook.md

    Returns:
        Complete formatted prompt string
    """
    # Check if this is an email task and build specialized prompt
    if task_content.strip().startswith('---') and 'type: email' in task_content:
        # Parse frontmatter to extract email data
        email_data = parse_email_frontmatter(task_content)
        if email_data:
            logging.info(f"Detected email task - using email classification prompt")
            return build_email_classification_prompt(task_file, task_content, email_data)
    
    # Use handbook content if provided, otherwise use default
    if handbook_content:
        company_rules = handbook_content
    else:
        company_rules = """
## Company Rules
- Tone: Professional and Concise
- Safety: Never take financial action without approval
- Task Handling: All tasks must move from /Needs_Action → /Done when complete
"""

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
    """
    Parse YAML frontmatter from email task content.
    
    Args:
        content: Full content of the email task file
        
    Returns:
        Dictionary with email fields or None if parsing fails
    """
    import re
    
    try:
        # Extract frontmatter between --- markers
        match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not match:
            return None
        
        frontmatter = match.group(1)
        email_data = {}
        
        # Parse key-value pairs
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
    """
    Ensures Dashboard.md is updated with:
    - Accurate Pending Tasks Count (based on folder state)
    - Incremented Completed Tasks Count
    - Current Last Processed timestamp
    - New recent activity entries
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate current pending (excluding metadata)
    pending_count = 0
    if os.path.exists(NEEDS_ACTION_DIR):
        pending_count = len([f for f in os.listdir(NEEDS_ACTION_DIR)
                            if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f))
                            and not f.endswith('_metadata.md')])

    # Read existing content
    if os.path.exists(DASHBOARD_FILE):
        with open(DASHBOARD_FILE, "r") as f:
            lines = f.readlines()
    else:
        # Create a default template if Dashboard.md does not exist
        lines = [
            "# Dashboard\n",
            "\n",
            "## System Status\n",
            "System operational\n",
            "\n",
            "## Pending Tasks Count\n",
            "0\n",
            "\n",
            "## Completed Tasks Count\n",
            "0\n",
            "\n",
            "## Last Processed\n",
            "Never\n",
            "\n",
            "## Recent Activity\n"
        ]

    new_lines = []
    skip_next_line = False

    for i, line in enumerate(lines):
        if skip_next_line:
            skip_next_line = False
            continue

        if "## Pending Tasks Count" in line:
            new_lines.append(line)
            new_lines.append(str(pending_count) + "\n")
            skip_next_line = True
        elif "## Completed Tasks Count" in line:
            new_lines.append(line)
            current_completed = 0
            if i + 1 < len(lines) and re.match(r'^\d+$', lines[i+1].strip()):
                current_completed = int(lines[i+1].strip())
            new_lines.append(str(current_completed + processed_count) + "\n")
            skip_next_line = True
        elif "## Last Processed" in line:
            new_lines.append(line)
            new_lines.append(now + "\n")
            skip_next_line = True
        elif "## Recent Activity" in line:
            new_lines.append(line)
            for name in processed_file_names:
                new_lines.append(f"- {now}: Processed file '{name}'\n")
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith('##'):
                    new_lines.append(lines[j])
                    break
                if lines[j].strip():
                    new_lines.append(lines[j])
            break
        else:
            new_lines.append(line)

    final_content = "".join(new_lines).strip() + "\n"

    with open(DASHBOARD_FILE, "w") as f:
        f.write(final_content)
    
    logging.info(f"Dashboard updated: {pending_count} pending, {processed_count} completed this cycle")


# ============================================================================
# Task Processing
# ============================================================================

def process_task_file(file_path: str, handbook_content: str = "") -> bool:
    """
    Process a single task file from Needs_Action/.
    
    Args:
        file_path: Full path to the task file
        handbook_content: Content from Company_Handbook.md
        
    Returns:
        True if processing succeeded, False otherwise
    """
    filename = os.path.basename(file_path)
    meta_path = os.path.join(NEEDS_ACTION_DIR, f"{os.path.splitext(filename)[0]}_metadata.md")
    
    logging.info(f"Processing task: {filename}")
    
    try:
        # Read task content
        with open(file_path, "r", encoding='utf-8') as f:
            content = f.read()
        
        # Skip empty files
        if not content.strip():
            logging.warning(f"Skipping empty file: {filename}")
            return False
        
        # Build the full prompt
        full_prompt = build_full_prompt(filename, content, handbook_content)
        
        # Print the complete prompt for manual copy-paste
        logging.info("=" * 80)
        logging.info("FULL PROMPT FOR AI PROCESSING:")
        logging.info("=" * 80)
        print("\n" + full_prompt)
        logging.info("=" * 80)
        logging.info("END OF PROMPT - Copy above for AI processing")
        logging.info("=" * 80)
        
        # Log to daily log file
        log_date = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(LOGS_DIR, f"{log_date}.md")
        with open(log_path, "a", encoding='utf-8') as log_file:
            log_file.write(f"\n## {datetime.now().strftime('%H:%M:%S')} - {filename}\n")
            log_file.write(f"**Prompt Length:** {len(full_prompt)} characters\n")
            log_file.write(f"**Status:** Prompt generated, awaiting AI response\n")
            log_file.write("---\n")
        
        # Move file to Done after prompt generation
        done_file_path = os.path.join(DONE_DIR, filename)
        
        if os.path.exists(done_file_path):
            logging.warning(f"File '{filename}' already exists in Done. Removing from Needs_Action.")
            os.remove(file_path)
            if os.path.exists(meta_path):
                os.remove(meta_path)
            return True
        
        shutil.copy2(file_path, done_file_path)
        
        if os.path.exists(done_file_path):
            logging.info(f"Successfully copied {filename} to Done")
            os.remove(file_path)
            logging.info(f"Removed {filename} from Needs_Action")
        else:
            logging.error(f"Copy failed for {filename}")
            return False
        
        # Move metadata file if exists
        if os.path.exists(meta_path):
            done_meta_path = os.path.join(DONE_DIR, os.path.basename(meta_path))
            shutil.copy2(meta_path, done_meta_path)
            if os.path.exists(done_meta_path):
                os.remove(meta_path)
                logging.info(f"Moved metadata to Done")
        
        # Update dashboard
        update_dashboard([filename], 1)
        
        logging.info(f"Task completed: {filename}")
        return True
        
    except Exception as e:
        logging.error(f"Failed to process {filename}: {e}")
        return False


class NeedsActionHandler(FileSystemEventHandler):
    """Watches Needs_Action/ directory for new task files."""
    
    def __init__(self, handbook_content: str = ""):
        self.handbook_content = handbook_content
        self.processing_lock = False
    
    def wait_for_file_stability(self, file_path: str, max_attempts: int = 10) -> bool:
        """Wait for file size to stabilize before processing."""
        last_size = -1
        for _ in range(max_attempts):
            if not os.path.exists(file_path):
                return False
            current_size = os.path.getsize(file_path)
            if current_size == last_size:
                return True
            last_size = current_size
            time.sleep(0.5)
        return False
    
    def on_created(self, event):
        """Handle new files in Needs_Action/."""
        if event.is_directory:
            return
        
        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Skip metadata files and hidden files
        if filename.endswith('_metadata.md') or filename.startswith('.'):
            return
        
        logging.info(f"New task detected: {filename}")
        
        # Wait for file to be fully written
        time.sleep(0.5)
        if not self.wait_for_file_stability(file_path):
            logging.warning(f"File {filename} not stable, skipping")
            return
        
        # Prevent concurrent processing
        if self.processing_lock:
            logging.info(f"Processor busy, will retry {filename}")
            return
        
        try:
            self.processing_lock = True
            process_task_file(file_path, self.handbook_content)
        finally:
            self.processing_lock = False


def process_all_pending():
    """Process all files currently in Needs_Action/."""
    if not os.path.exists(NEEDS_ACTION_DIR):
        logging.info("Needs_Action directory does not exist")
        update_dashboard([], 0)
        return
    
    # Load handbook content
    handbook_content = ""
    if os.path.exists(COMPANY_HANDBOOK_FILE):
        with open(COMPANY_HANDBOOK_FILE, "r", encoding='utf-8') as f:
            handbook_content = f.read()
        logging.info(f"Loaded Company Handbook ({len(handbook_content)} chars)")
    
    # Get all primary files (excluding metadata)
    all_files = os.listdir(NEEDS_ACTION_DIR)
    primary_files = [f for f in all_files 
                     if os.path.isfile(os.path.join(NEEDS_ACTION_DIR, f)) 
                     and not f.endswith('_metadata.md')]
    
    if not primary_files:
        logging.info("No pending tasks in Needs_Action/")
        update_dashboard([], 0)
        return
    
    logging.info(f"Found {len(primary_files)} pending task(s)")
    
    processed_count = 0
    processed_names = []
    
    for filename in primary_files:
        file_path = os.path.join(NEEDS_ACTION_DIR, filename)
        if process_task_file(file_path, handbook_content):
            processed_count += 1
            processed_names.append(filename)
    
    update_dashboard(processed_names, processed_count)
    logging.info(f"Processed {processed_count}/{len(primary_files)} tasks")


# ============================================================================
# Daily Briefing Mode
# ============================================================================

def generate_daily_briefing():
    """
    Generate a weekly briefing from Business_Goals.md and recent Done/ files.
    Creates: Briefings/YYYY-MM-DD_Monday_Briefing.md
    """
    logging.info("Generating daily briefing...")
    
    # Load Business Goals
    business_goals = ""
    if os.path.exists(BUSINESS_GOALS_FILE):
        with open(BUSINESS_GOALS_FILE, "r", encoding='utf-8') as f:
            business_goals = f.read()
        logging.info(f"Loaded Business Goals ({len(business_goals)} chars)")
    else:
        logging.warning(f"{BUSINESS_GOALS_FILE} not found")
    
    # Get last 7 days of completed tasks
    seven_days_ago = datetime.now() - timedelta(days=7)
    completed_tasks = []
    
    if os.path.exists(DONE_DIR):
        for filename in os.listdir(DONE_DIR):
            if filename.endswith('.md') or filename.endswith('.txt'):
                file_path = os.path.join(DONE_DIR, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime >= seven_days_ago:
                        with open(file_path, "r", encoding='utf-8') as f:
                            content = f.read(500)  # First 500 chars
                        completed_tasks.append({
                            'filename': filename,
                            'completed': mtime.strftime('%Y-%m-%d'),
                            'content': content[:200] + '...' if len(content) > 200 else content
                        })
                except Exception as e:
                    logging.debug(f"Error reading {filename}: {e}")
    
    completed_tasks.sort(key=lambda x: x['completed'], reverse=True)
    logging.info(f"Found {len(completed_tasks)} completed tasks in last 7 days")
    
    # Generate briefing
    today = datetime.now()
    briefing_date = today.strftime('%Y-%m-%d')
    day_name = today.strftime('%A')
    briefing_filename = f"{briefing_date}_{day_name}_Briefing.md"
    briefing_path = os.path.join(BRIEFINGS_DIR, briefing_filename)
    
    briefing_content = f"""---
type: daily_briefing
generated: {today.strftime('%Y-%m-%d %H:%M:%S')}
period: {seven_days_ago.strftime('%Y-%m-%d')} to {briefing_date}
tasks_completed: {len(completed_tasks)}
---

# Weekly Briefing: {day_name}, {briefing_date}

## Executive Summary

**Period:** {seven_days_ago.strftime('%Y-%m-%d')} → {briefing_date}  
**Tasks Completed:** {len(completed_tasks)}  
**System Status:** Operational

---

## Business Goals Reference

```
{business_goals if business_goals else '(No Business_Goals.md found)'}
```

---

## Completed Tasks (Last 7 Days)

"""
    
    if completed_tasks:
        for task in completed_tasks:
            briefing_content += f"""
### {task['filename']}
- **Completed:** {task['completed']}
- **Preview:** {task['content']}

"""
    else:
        briefing_content += "\n_No tasks completed in the last 7 days._\n"
    
    briefing_content += f"""
---

## Recommendations

1. Review completed tasks for quality assurance
2. Identify patterns in task types for process improvement
3. Check Pending_Approval/ for items awaiting decision
4. Review Plans/ for multi-step task progress

---

## Next Actions

- [ ] Review this briefing
- [ ] Address any pending approvals
- [ ] Plan upcoming week priorities

---

*Generated by AI Employee Orchestrator*
"""
    
    # Write briefing
    with open(briefing_path, "w", encoding='utf-8') as f:
        f.write(briefing_content)
    
    logging.info(f"Briefing generated: {briefing_path}")
    print(f"\n{'='*60}")
    print(f"BRIEFING GENERATED: {briefing_path}")
    print(f"{'='*60}\n")
    
    return briefing_path


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main orchestrator entry point."""
    parser = argparse.ArgumentParser(
        description="AI Employee Orchestrator - Central Brain Connector"
    )
    parser.add_argument(
        '--mode',
        type=str,
        default='watch',
        choices=['watch', 'daily-briefing', 'process-once'],
        help='Operation mode: watch (default), daily-briefing, or process-once'
    )
    
    args = parser.parse_args()
    
    logging.info("=" * 60)
    logging.info("AI Employee Orchestrator Starting...")
    logging.info(f"Mode: {args.mode}")
    logging.info(f"DRY_RUN: {DRY_RUN}")
    logging.info(f"OPENAI_API_BASE: {OPENAI_API_BASE or '(not set)'}")
    logging.info("=" * 60)
    
    # Handle different modes
    if args.mode == 'daily-briefing':
        generate_daily_briefing()
        return
    
    if args.mode == 'process-once':
        process_all_pending()
        return
    
    # Watch mode (default)
    logging.info("Loading Company Handbook...")
    handbook_content = ""
    if os.path.exists(COMPANY_HANDBOOK_FILE):
        with open(COMPANY_HANDBOOK_FILE, "r", encoding='utf-8') as f:
            handbook_content = f.read()
        logging.info(f"Company Handbook loaded ({len(handbook_content)} chars)")
    
    # Process any existing files first
    logging.info("Processing existing pending tasks...")
    process_all_pending()
    
    # Setup watchdog
    logging.info(f"Starting watchdog on {NEEDS_ACTION_DIR}/")
    event_handler = NeedsActionHandler(handbook_content)
    observer = Observer()
    observer.schedule(event_handler, NEEDS_ACTION_DIR, recursive=False)
    observer.start()
    
    logging.info("Orchestrator is now watching for new tasks...")
    logging.info("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Orchestrator stopped by user")
        observer.stop()
    
    observer.join()
    logging.info("Orchestrator shutdown complete")


if __name__ == "__main__":
    main()
