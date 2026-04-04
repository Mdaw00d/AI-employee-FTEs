#!/usr/bin/env python3
"""
Weekly Audit - Gold Tier CEO Briefing Generator
================================================
Generates comprehensive weekly CEO briefings by analyzing business data,
completed tasks, accounting records, and Odoo transactions.

Scheduled Run:
    # Run every Monday at 6:00 AM for the previous week
    # Cron example (Linux/Mac):
    0 6 * * 1 /path/to/python /path/to/weekly_audit.py >> Logs/weekly_audit.log 2>&1
    
    # Windows Task Scheduler equivalent:
    # Create task to run: python weekly_audit.py
    # Trigger: Weekly on Monday at 6:00 AM

Usage:
    python weekly_audit.py                    # Generate weekly briefing
    python weekly_audit.py --dry-run          # Preview without writing files
    python weekly_audit.py --week=2026-W10    # Generate for specific week

Environment Variables:
    OPENAI_API_BASE     - API endpoint for AI calls (optional)
    OPENAI_API_KEY      - API key for AI calls (optional)
    DRY_RUN             - If 'true', only print without writing
"""

import os
import sys
import io
import json
import logging
import argparse
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ============================================================================
# Configuration
# ============================================================================

LOGS_DIR = "./Logs"
DONE_DIR = "./Done"
BRIEFINGS_DIR = "./Briefings"
DASHBOARD_FILE = "./Dashboard.md"
COMPANY_HANDBOOK_FILE = "./Company_Handbook.md"
BUSINESS_GOALS_FILE = "./Business_Goals.md"
ACCOUNTING_DIR = "./Accounting"
PLANS_DIR = "./Plans"
PENDING_APPROVAL_DIR = "./Pending_Approval"
APPROVED_DIR = "./Approved"
INBOX_DIR = "./Inbox"

# MCP Server URLs
MCP_SERVERS = {
    'email': 'http://localhost:8000/rpc',
    'social': 'http://localhost:8001/rpc',
    'browser': 'http://localhost:8002/rpc',
    'odoo': 'http://localhost:8070/rpc',
}

# Ensure directories exist
for directory in [LOGS_DIR, DONE_DIR, BRIEFINGS_DIR, ACCOUNTING_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'weekly_audit.log'), encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

# Environment configuration
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


# ============================================================================
# MCP Client
# ============================================================================

def call_mcp_server(server_name: str, method: str, params: Dict = None, timeout: int = 30) -> Dict:
    """
    Call an MCP server via JSON-RPC.
    
    Args:
        server_name: Name of the MCP server
        method: RPC method to call
        params: Method parameters
        timeout: Request timeout in seconds
    
    Returns:
        Dict with result or error
    """
    if server_name not in MCP_SERVERS:
        return {'success': False, 'error': f'Unknown MCP server: {server_name}'}
    
    url = MCP_SERVERS[server_name]
    
    request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1
    }
    
    try:
        logging.info(f"Calling MCP {server_name}: {method}")
        
        data = json.dumps(request).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            
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
        logging.warning(f"MCP {server_name} connection error: {e}")
        return {
            'success': False,
            'error': f'Connection error: {str(e)}',
            'server': server_name,
            'server_offline': True
        }
    except Exception as e:
        logging.warning(f"MCP {server_name} error: {e}")
        return {
            'success': False,
            'error': str(e),
            'server': server_name
        }


# ============================================================================
# Data Collection Functions
# ============================================================================

def get_week_range(target_date: datetime = None) -> Tuple[datetime, datetime]:
    """
    Get the Monday-Sunday range for the week containing target_date.
    If no date provided, uses last week (previous Monday to Sunday).
    
    Returns:
        Tuple of (week_start, week_end) datetime objects
    """
    if target_date is None:
        # Default to last week
        today = datetime.now()
        # Go back to find last Monday
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)
    else:
        days_since_monday = target_date.weekday()
        last_monday = target_date - timedelta(days=days_since_monday)
    
    week_start = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7) - timedelta(seconds=1)
    
    return week_start, week_end


def get_done_files(week_start: datetime, week_end: datetime) -> List[Dict]:
    """
    Scan Done/ directory for files completed within the week.
    
    Returns:
        List of dicts with file info and content
    """
    done_items = []
    
    if not os.path.exists(DONE_DIR):
        logging.warning(f"Done directory not found: {DONE_DIR}")
        return done_items
    
    for filename in os.listdir(DONE_DIR):
        if not filename.endswith('.md'):
            continue
        
        filepath = os.path.join(DONE_DIR, filename)
        
        try:
            # Try to extract date from filename
            date_match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
            if date_match:
                year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                file_date = datetime(year, month, day)
                
                if week_start <= file_date <= week_end:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Categorize by type
                    file_type = 'task'
                    if filename.startswith('FB_'):
                        file_type = 'facebook'
                    elif filename.startswith('IG_'):
                        file_type = 'instagram'
                    elif filename.startswith('X_'):
                        file_type = 'x'
                    elif 'LINKEDIN' in filename.upper():
                        file_type = 'linkedin'
                    elif 'EMAIL' in filename.upper():
                        file_type = 'email'
                    elif 'INVOICE' in filename.upper() or 'ACCOUNTING' in filename.upper():
                        file_type = 'accounting'
                    
                    done_items.append({
                        'filename': filename,
                        'filepath': filepath,
                        'date': file_date,
                        'type': file_type,
                        'content': content
                    })
        except Exception as e:
            logging.warning(f"Error reading {filename}: {e}")
    
    return done_items


def get_pending_approvals() -> List[Dict]:
    """
    Get all pending approval files with age analysis.
    
    Returns:
        List of approval items with age categorization
    """
    approvals = []
    
    if not os.path.exists(PENDING_APPROVAL_DIR):
        return approvals
    
    now = datetime.now()
    
    for filename in os.listdir(PENDING_APPROVAL_DIR):
        if not filename.endswith('.md'):
            continue
        
        filepath = os.path.join(PENDING_APPROVAL_DIR, filename)
        
        try:
            # Get file creation/modification time
            stat = os.stat(filepath)
            created = datetime.fromtimestamp(stat.st_ctime)
            age_hours = (now - created).total_seconds() / 3600
            
            # Categorize by age
            if age_hours < 24:
                age_category = '< 24 hours'
            elif age_hours < 48:
                age_category = '24-48 hours'
            else:
                age_category = '> 48 hours'
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract priority/type from content
            priority = 'normal'
            approval_type = 'general'
            
            if 'priority: high' in content.lower() or 'urgent' in content.lower():
                priority = 'high'
            elif 'priority: low' in content.lower():
                priority = 'low'
            
            if 'type: social' in content.lower():
                approval_type = 'social_media'
            elif 'type: email' in content.lower():
                approval_type = 'email'
            elif 'payment' in content.lower() or 'invoice' in content.lower():
                approval_type = 'financial'
                priority = 'high'  # Financial items are high priority
            
            approvals.append({
                'filename': filename,
                'filepath': filepath,
                'created': created,
                'age_hours': age_hours,
                'age_category': age_category,
                'priority': priority,
                'type': approval_type,
                'content': content
            })
            
        except Exception as e:
            logging.warning(f"Error reading approval {filename}: {e}")
    
    return approvals


def get_business_goals() -> Dict:
    """
    Read business goals from Business_Goals.md.
    
    Returns:
        Dict with goals and targets
    """
    goals = {
        'goals': [],
        'quarterly_targets': {},
        'kpis': {}
    }
    
    if not os.path.exists(BUSINESS_GOALS_FILE):
        logging.warning(f"Business goals file not found: {BUSINESS_GOALS_FILE}")
        # Return default goals template
        return goals
    
    try:
        with open(BUSINESS_GOALS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse goals from markdown
        # Expected format:
        # ## Q1 2026 Goals
        # - Revenue: $2.5M
        # - Customer Acquisition: 500
        
        goals_match = re.findall(r'-\s*([^:]+):\s*(.+)', content)
        for name, value in goals_match:
            goals['goals'].append({
                'name': name.strip(),
                'target': value.strip(),
                'current': None,
                'progress': None
            })
        
    except Exception as e:
        logging.error(f"Error reading business goals: {e}")
    
    return goals


def get_odoo_transactions(week_start: datetime, week_end: datetime) -> Dict:
    """
    Fetch transactions from Odoo via MCP for the week.
    
    Returns:
        Dict with transaction summary
    """
    transactions = {
        'invoices': [],
        'payments': [],
        'total_revenue': 0,
        'total_payments': 0,
        'outstanding_ar': 0,
        'error': None
    }
    
    # Try to get transactions from Odoo MCP
    result = call_mcp_server('odoo', 'get_transactions', {
        'date_from': week_start.strftime('%Y-%m-%d'),
        'date_to': week_end.strftime('%Y-%m-%d')
    })
    
    if result.get('success'):
        data = result.get('result', {})
        transactions['invoices'] = data.get('invoices', [])
        transactions['payments'] = data.get('payments', [])
        transactions['total_revenue'] = data.get('total_revenue', 0)
        transactions['total_payments'] = data.get('total_payments', 0)
        transactions['outstanding_ar'] = data.get('outstanding_ar', 0)
    else:
        if not result.get('server_offline'):
            transactions['error'] = result.get('error', 'Unknown error')
        else:
            transactions['error'] = 'Odoo MCP server offline'
    
    return transactions


def get_accounting_summary(week_start: datetime, week_end: datetime) -> Dict:
    """
    Read accounting data from Accounting/ directory.
    
    Returns:
        Dict with accounting summary
    """
    summary = {
        'invoices_created': 0,
        'payments_processed': 0,
        'total_value': 0,
        'transactions': [],
        'anomalies': []
    }
    
    if not os.path.exists(ACCOUNTING_DIR):
        logging.warning(f"Accounting directory not found: {ACCOUNTING_DIR}")
        return summary
    
    # Look for current month or weekly files
    for filename in os.listdir(ACCOUNTING_DIR):
        if not filename.endswith('.md'):
            continue
        
        filepath = os.path.join(ACCOUNTING_DIR, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Count invoices and payments
            invoice_matches = re.findall(r'invoice|Invoice|INVOICE', content)
            payment_matches = re.findall(r'payment|Payment|PAYMENT', content)
            
            summary['invoices_created'] += len(invoice_matches)
            summary['payments_processed'] += len(payment_matches)
            
            # Try to extract monetary values
            money_matches = re.findall(r'\$?[\d,]+\.?\d*', content)
            for match in money_matches:
                try:
                    value = float(match.replace('$', '').replace(',', ''))
                    if value > 100:  # Filter out small numbers
                        summary['total_value'] += value
                except:
                    pass
            
        except Exception as e:
            logging.warning(f"Error reading accounting file {filename}: {e}")
    
    return summary


def analyze_social_performance(week_start: datetime, week_end: datetime) -> Dict:
    """
    Analyze social media performance from Done/ files.
    
    Returns:
        Dict with social media metrics
    """
    metrics = {
        'posts': 0,
        'platforms': {},
        'engagement_estimate': 0,
        'top_content': []
    }
    
    done_files = get_done_files(week_start, week_end)
    
    for item in done_files:
        if item['type'] in ['facebook', 'instagram', 'x', 'linkedin']:
            metrics['posts'] += 1
            
            platform = item['type']
            if platform not in metrics['platforms']:
                metrics['platforms'][platform] = 0
            metrics['platforms'][platform] += 1
            
            # Estimate engagement from content length and type
            content_length = len(item.get('content', ''))
            if content_length > 500:
                metrics['engagement_estimate'] += 100
            else:
                metrics['engagement_estimate'] += 50
    
    return metrics


# ============================================================================
# Proactive Suggestions Engine
# ============================================================================

def generate_proactive_suggestions(data: Dict) -> List[Dict]:
    """
    Generate proactive suggestions based on analyzed data.
    
    Examples:
    - Cancel unused subscriptions
    - Follow up on old invoices
    - Address pending approvals
    - Optimize posting schedule
    
    Returns:
        List of suggestion dicts
    """
    suggestions = []
    
    # Check for stale pending approvals
    approvals = data.get('pending_approvals', [])
    stale_approvals = [a for a in approvals if a.get('age_category') == '> 48 hours']
    if stale_approvals:
        suggestions.append({
            'priority': 'high',
            'category': 'Approvals',
            'title': 'Review Stale Pending Approvals',
            'description': f'{len(stale_approvals)} approval(s) pending for more than 48 hours require immediate attention.',
            'action': 'Review items in Pending_Approval/ directory',
            'impact': 'Prevent delays in operations and potential late fees'
        })
    
    # Check for financial anomalies
    accounting = data.get('accounting', {})
    odoo = data.get('odoo', {})
    
    if odoo.get('outstanding_ar', 0) > 50000:
        suggestions.append({
            'priority': 'high',
            'category': 'Finance',
            'title': 'High Outstanding Receivables',
            'description': f'Outstanding accounts receivable: ${odoo.get("outstanding_ar", 0):,.2f}',
            'action': 'Review aging report and initiate collection efforts',
            'impact': 'Improve cash flow'
        })
    
    # Check for unused subscriptions (pattern matching in accounting)
    if accounting.get('total_value', 0) > 0:
        # Look for recurring payment patterns
        suggestions.append({
            'priority': 'medium',
            'category': 'Cost Optimization',
            'title': 'Review Recurring Subscriptions',
            'description': 'Audit monthly recurring expenses for unused services',
            'action': 'Review Accounting/ for subscription payments and cancel unused services',
            'impact': 'Potential cost savings of 10-20% on operational expenses'
        })
    
    # Social media optimization
    social = data.get('social', {})
    if social.get('posts', 0) < 5:
        suggestions.append({
            'priority': 'low',
            'category': 'Marketing',
            'title': 'Increase Social Media Activity',
            'description': f'Only {social.get("posts", 0)} posts this week',
            'action': 'Schedule more frequent posts across platforms',
            'impact': 'Improved brand visibility and engagement'
        })
    
    # Task completion rate
    done = data.get('done_items', [])
    if len(done) < 10:
        suggestions.append({
            'priority': 'medium',
            'category': 'Operations',
            'title': 'Low Task Completion Rate',
            'description': f'Only {len(done)} tasks completed this week',
            'action': 'Review inbox and pending items for backlog',
            'impact': 'Improved operational efficiency'
        })
    
    return suggestions


# ============================================================================
# Briefing Generation
# ============================================================================

def generate_executive_summary(data: Dict) -> str:
    """Generate 3-5 key executive summary points."""
    points = []
    
    # Revenue point
    odoo = data.get('odoo', {})
    if odoo.get('total_revenue', 0) > 0:
        points.append(f"**Revenue Operations**: ${odoo.get('total_revenue', 0):,.2f} in transactions processed")
    
    # Task completion point
    done = data.get('done_items', [])
    if done:
        by_type = {}
        for item in done:
            t = item.get('type', 'other')
            by_type[t] = by_type.get(t, 0) + 1
        total = sum(by_type.values())
        points.append(f"**Task Completion**: {total} tasks completed across {len(by_type)} categories")
    
    # Pending approvals point
    approvals = data.get('pending_approvals', [])
    if approvals:
        high_priority = len([a for a in approvals if a.get('priority') == 'high'])
        if high_priority > 0:
            points.append(f"**Attention Required**: {high_priority} high-priority approval(s) pending")
        else:
            points.append(f"**Approvals**: {len(approvals)} items pending review")
    
    # Social media point
    social = data.get('social', {})
    if social.get('posts', 0) > 0:
        points.append(f"**Social Media**: {social.get('posts', 0)} posts published this week")
    
    # Ensure we have at least 3 points
    while len(points) < 3:
        points.append("**Operations**: System functioning normally")
    
    return '\n\n'.join([f"{i+1}. {p}" for i, p in enumerate(points[:5])])


def generate_briefing(week_start: datetime, week_end: datetime, data: Dict) -> str:
    """
    Generate the complete CEO briefing document.
    
    Args:
        week_start: Start of the week
        week_end: End of the week
        data: Collected and analyzed data
    
    Returns:
        Complete briefing markdown content
    """
    week_num = week_start.isocalendar()[1]
    year = week_start.year
    
    # Format dates for display
    week_start_str = week_start.strftime('%Y-%m-%d')
    week_end_str = week_end.strftime('%Y-%m-%d')
    generated_str = datetime.now().strftime('%Y-%m-%d %I:%M %p')
    
    # Get data components
    odoo = data.get('odoo', {})
    accounting = data.get('accounting', {})
    social = data.get('social', {})
    approvals = data.get('pending_approvals', [])
    suggestions = data.get('suggestions', [])
    done_items = data.get('done_items', [])
    
    # Count by category
    tasks_by_type = {}
    for item in done_items:
        t = item.get('type', 'other')
        tasks_by_type[t] = tasks_by_type.get(t, 0) + 1
    
    # Approval age breakdown
    approvals_by_age = {'< 24 hours': 0, '24-48 hours': 0, '> 48 hours': 0}
    for a in approvals:
        age = a.get('age_category', '< 24 hours')
        approvals_by_age[age] = approvals_by_age.get(age, 0) + 1
    
    briefing = f"""# CEO Weekly Briefing

**Week**: {year}-W{week_num:02d} ({week_start_str} - {week_end_str})
**Generated**: {generated_str}
**Prepared By**: AI Operations Assistant

---

## Executive Summary

{generate_executive_summary(data)}

---

## Revenue

| Metric | This Week | Status |
|--------|-----------|--------|
| Total Revenue | ${odoo.get('total_revenue', 0):,.2f} | {'🟢' if odoo.get('total_revenue', 0) > 0 else '🟡'} |
| Payments Received | ${odoo.get('total_payments', 0):,.2f} | - |
| Outstanding AR | ${odoo.get('outstanding_ar', 0):,.2f} | {'⚠️' if odoo.get('outstanding_ar', 0) > 50000 else '🟢'} |
| Invoices Created | {accounting.get('invoices_created', 0)} | - |
| Payments Processed | {accounting.get('payments_processed', 0)} | - |

**Notes**:
- Data sourced from Odoo ERP via MCP
- {'Odoo server online' if not odoo.get('error') else f"⚠️ {odoo.get('error', 'Unknown error')}"}

---

## Completed Tasks

**Total Completed**: {len(done_items)} tasks

| Category | Count | Percentage |
|----------|-------|------------|
"""
    
    total_tasks = len(done_items) if len(done_items) > 0 else 1
    for task_type, count in sorted(tasks_by_type.items(), key=lambda x: -x[1]):
        pct = (count / total_tasks) * 100
        briefing += f"| {task_type.title()} | {count} | {pct:.1f}% |\n"
    
    briefing += f"""| **Total** | **{len(done_items)}** | **100%** |

### Recent Completed Items
"""
    
    # List up to 10 recent items
    recent = sorted(done_items, key=lambda x: x.get('date', datetime.min), reverse=True)[:10]
    for item in recent:
        briefing += f"- `{item['filename']}` ({item['type']})\n"
    
    if not recent:
        briefing += "- No tasks completed this week\n"
    
    briefing += f"""
---

## Bottlenecks

### Pending Approvals: {len(approvals)} items

| Age | Count | Priority Items |
|-----|-------|----------------|
| < 24 hours | {approvals_by_age.get('< 24 hours', 0)} | {len([a for a in approvals if a.get('age_category') == '< 24 hours' and a.get('priority') == 'high'])} |
| 24-48 hours | {approvals_by_age.get('24-48 hours', 0)} | {len([a for a in approvals if a.get('age_category') == '24-48 hours' and a.get('priority') == 'high'])} |
| > 48 hours | {approvals_by_age.get('> 48 hours', 0)} | {len([a for a in approvals if a.get('age_category') == '> 48 hours' and a.get('priority') == 'high'])} |

"""
    
    # List high-priority stale approvals
    stale_high = [a for a in approvals if a.get('age_category') in ['> 48 hours', '24-48 hours'] and a.get('priority') == 'high']
    if stale_high:
        briefing += "**⚠️ Action Required - High Priority Stale Approvals:**\n\n"
        for item in stale_high:
            briefing += f"- `{item['filename']}` ({item['age_category']})\n"
        briefing += "\n"
    
    # Identify other bottlenecks
    briefing += """### Other Bottlenecks

"""
    
    if not stale_high and len(approvals) == 0:
        briefing += "No significant bottlenecks identified.\n"
    else:
        if len(approvals) > 10:
            briefing += f"- High volume of pending approvals ({len(approvals)} items)\n"
        if accounting.get('invoices_created', 0) == 0:
            briefing += "- No invoices created this week - review billing pipeline\n"
    
    briefing += f"""
---

## Proactive Suggestions

"""
    
    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            priority_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(sug.get('priority', 'low'), '🟢')
            briefing += f"""### {priority_icon} {i}. {sug.get('title', 'Suggestion')}

**Category**: {sug.get('category', 'General')}
**Description**: {sug.get('description', '')}
**Recommended Action**: {sug.get('action', '')}
**Expected Impact**: {sug.get('impact', '')}

"""
    else:
        briefing += "No proactive suggestions at this time.\n"
    
    briefing += f"""
---

## Appendix

### Data Sources
- **Done/**: {len(done_items)} completed task files analyzed
- **Pending_Approval/**: {len(approvals)} pending items
- **Accounting/**: Summary extracted
- **Odoo ERP**: Transaction data via MCP {'(online)' if not odoo.get('error') else '(offline)'}
- **Business_Goals.md**: Goal tracking {'(found)' if os.path.exists(BUSINESS_GOALS_FILE) else '(not found)'}

### Files Generated
- Briefing: `Briefings/{year}-{week_start_str[5:7]}-{week_start_str[8:10]}_Monday_Briefing.md`
- This report auto-appends summary to `Dashboard.md`

---

**Next Briefing**: {(week_start + timedelta(days=7)).strftime('%Y-%m-%d')} (Week {year}-W{(week_start + timedelta(days=7)).isocalendar()[1]:02d})
"""
    
    return briefing


def append_to_dashboard(briefing_file: str, week_start: datetime, data: Dict):
    """Append weekly summary to Dashboard.md."""
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    week_num = week_start.isocalendar()[1]
    
    # Prepare summary line
    summary_lines = [
        f"- {now}: Weekly Briefing generated (Week {week_start.year}-W{week_num:02d})",
    ]
    
    # Add key metrics
    odoo = data.get('odoo', {})
    if odoo.get('total_revenue', 0) > 0:
        summary_lines.append(f"- {now}: Weekly revenue ${odoo.get('total_revenue', 0):,.2f}")
    
    done_items = data.get('done_items', [])
    if done_items:
        summary_lines.append(f"- {now}: {len(done_items)} tasks completed this week")
    
    approvals = data.get('pending_approvals', [])
    if approvals:
        summary_lines.append(f"- {now}: {len(approvals)} approvals pending")
    
    if not os.path.exists(DASHBOARD_FILE):
        # Create dashboard
        content = "# Dashboard\n\n## System Status\nSystem operational\n\n## Weekly Briefings\n"
    else:
        with open(DASHBOARD_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if Weekly Briefings section exists
        if '## Weekly Briefings' not in content:
            content += "\n## Weekly Briefings\n"
    
    # Find where to insert (after Weekly Briefings header)
    lines = content.split('\n')
    new_lines = []
    inserted = False
    
    for line in lines:
        new_lines.append(line)
        if '## Weekly Briefings' in line and not inserted:
            for summary_line in summary_lines:
                new_lines.append(summary_line)
            inserted = True
    
    if not inserted:
        # Append at end
        for summary_line in summary_lines:
            new_lines.append(summary_line)
    
    with open(DASHBOARD_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    
    logging.info(f"Dashboard updated with weekly briefing summary")


# ============================================================================
# Main Execution
# ============================================================================

def run_weekly_audit(target_date: datetime = None, dry_run: bool = False) -> str:
    """
    Execute the weekly audit process.
    
    Args:
        target_date: Date to generate briefing for (default: last week)
        dry_run: If True, only print without writing files
    
    Returns:
        Path to generated briefing file
    """
    logging.info("=" * 80)
    logging.info("WEEKLY AUDIT - CEO BRIEFING GENERATION")
    logging.info("=" * 80)
    
    # Get week range
    week_start, week_end = get_week_range(target_date)
    logging.info(f"Week Range: {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")
    
    # Collect data
    logging.info("Collecting data...")
    
    logging.info("  - Scanning Done/ directory...")
    done_items = get_done_files(week_start, week_end)
    logging.info(f"    Found {len(done_items)} completed items")
    
    logging.info("  - Checking Pending_Approval/...")
    pending_approvals = get_pending_approvals()
    logging.info(f"    Found {len(pending_approvals)} pending approvals")
    
    logging.info("  - Reading business goals...")
    business_goals = get_business_goals()
    logging.info(f"    Found {len(business_goals.get('goals', []))} goals")
    
    logging.info("  - Fetching Odoo transactions...")
    odoo_data = get_odoo_transactions(week_start, week_end)
    if odoo_data.get('error'):
        logging.warning(f"    Odoo error: {odoo_data.get('error')}")
    else:
        logging.info(f"    Revenue: ${odoo_data.get('total_revenue', 0):,.2f}")
    
    logging.info("  - Reading accounting data...")
    accounting_data = get_accounting_summary(week_start, week_end)
    logging.info(f"    Invoices: {accounting_data.get('invoices_created', 0)}, Payments: {accounting_data.get('payments_processed', 0)}")
    
    logging.info("  - Analyzing social media performance...")
    social_data = analyze_social_performance(week_start, week_end)
    logging.info(f"    Posts: {social_data.get('posts', 0)}")
    
    # Compile data
    data = {
        'week_start': week_start,
        'week_end': week_end,
        'done_items': done_items,
        'pending_approvals': pending_approvals,
        'business_goals': business_goals,
        'odoo': odoo_data,
        'accounting': accounting_data,
        'social': social_data,
    }
    
    # Generate proactive suggestions
    logging.info("Generating proactive suggestions...")
    suggestions = generate_proactive_suggestions(data)
    data['suggestions'] = suggestions
    logging.info(f"  Generated {len(suggestions)} suggestions")
    
    # Generate briefing
    logging.info("Generating CEO briefing...")
    briefing_content = generate_briefing(week_start, week_end, data)
    
    # Create briefing filename
    week_num = week_start.isocalendar()[1]
    briefing_filename = f"{week_start.strftime('%Y-%m-%d')}_Monday_Briefing.md"
    briefing_path = os.path.join(BRIEFINGS_DIR, briefing_filename)
    
    if dry_run:
        logging.info("\n" + "=" * 80)
        logging.info("DRY RUN - Briefing content (not saved):")
        logging.info("=" * 80)
        print(briefing_content)
        logging.info("=" * 80)
        logging.info("DRY RUN COMPLETE - No files written")
        return None
    
    # Write briefing file
    logging.info(f"Writing briefing to {briefing_path}...")
    with open(briefing_path, 'w', encoding='utf-8') as f:
        f.write(briefing_content)
    logging.info(f"Briefing saved: {briefing_path}")
    
    # Update dashboard
    logging.info("Updating Dashboard.md...")
    append_to_dashboard(briefing_path, week_start, data)
    
    logging.info("=" * 80)
    logging.info("WEEKLY AUDIT COMPLETE")
    logging.info(f"Briefing: {briefing_path}")
    logging.info(f"Dashboard: {DASHBOARD_FILE}")
    logging.info("=" * 80)
    
    return briefing_path


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Weekly Audit - Generate CEO Briefing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python weekly_audit.py                    # Generate for last week
    python weekly_audit.py --dry-run          # Preview without writing
    python weekly_audit.py --week=2026-W10    # Generate for specific week
    python weekly_audit.py --date=2026-03-10  # Generate for week containing date

Cron Schedule (Linux/Mac):
    # Run every Monday at 6:00 AM
    0 6 * * 1 /path/to/python /path/to/weekly_audit.py >> Logs/weekly_audit.log 2>&1

Windows Task Scheduler:
    # Create task to run weekly on Monday at 6:00 AM
    # Action: python C:\\path\\to\\weekly_audit.py
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview briefing without writing files'
    )
    
    parser.add_argument(
        '--week',
        type=str,
        help='ISO week to generate (e.g., 2026-W10)'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='Date to find week for (YYYY-MM-DD format)'
    )
    
    args = parser.parse_args()
    
    # Determine target date
    target_date = None
    
    if args.week:
        # Parse ISO week
        match = re.match(r'(\d{4})-W(\d{2})', args.week)
        if match:
            year, week = int(match.group(1)), int(match.group(2))
            # Find Monday of that week
            jan_first = datetime(year, 1, 1)
            target_date = jan_first + timedelta(weeks=week - 1)
            target_date = target_date - timedelta(days=target_date.weekday())
        else:
            logging.error(f"Invalid week format: {args.week}. Use YYYY-Www format.")
            sys.exit(1)
    
    elif args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logging.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD format.")
            sys.exit(1)
    
    # Run audit
    dry_run = args.dry_run or DRY_RUN
    briefing_path = run_weekly_audit(target_date=target_date, dry_run=dry_run)
    
    if briefing_path:
        print(f"\n✓ Weekly briefing generated: {briefing_path}")
        print(f"✓ Dashboard updated: {DASHBOARD_FILE}")


if __name__ == '__main__':
    main()
