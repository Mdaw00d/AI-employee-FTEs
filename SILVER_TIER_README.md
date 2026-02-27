# Silver Tier - Personal AI Employee

**Status:** ✅ Complete
**Hackathon:** Personal AI Employee

---

## Deliverables Checklist

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| ≥2 Watchers | ✅ | Gmail, LinkedIn, WhatsApp |
| Automatic Posting | ✅ | `linkedin_poster.py` |
| Reasoning Loop (Plan.md) | ✅ | Orchestrator → Qwen prompt |
| External Action | ✅ | LinkedIn posting + Email drafts |
| Human-in-the-Loop | ✅ | Pending_Approval → Approved workflow |
| Basic Scheduling | ✅ | PM2 / Task Scheduler support |
| Agent Skills | ✅ | `Skills/process_email/`, `Skills/process_task/` |

---

## File Structure

```
bronze-tier/
├── gmail_watcher.py          # Polls Gmail API every 120s
├── linkedin_watcher.py       # Monitors LinkedIn messages
├── whatsapp_watcher.py       # Monitors WhatsApp messages
├── linkedin_poster.py        # Posts to LinkedIn automatically
├── orchestrator.py           # Central brain - processes tasks
├── email_reply_approver.py   # Processes approved email replies
│
├── credentials.json          # Gmail OAuth (you provide)
├── token.json               # Gmail OAuth token (auto-generated)
├── processed_ids.pkl         # Track processed emails
│
├── Needs_Action/            # New tasks arrive here
├── Plans/                   # AI-created plans
├── Pending_Approval/        # Awaiting human approval
├── Approved/                # Ready to execute
├── Done/                    # Completed tasks
├── Logs/                    # All watcher logs
└── Skills/
    ├── process_email/       # Email processing skill
    └── process_task/        # General task skill
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Gmail OAuth (First Time Only)

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 credentials (Desktop app)
3. Download as `credentials.json` in project root
4. Run authentication:

```bash
python gmail_watcher.py
# Browser opens → Login → Accept permissions
# token.json created automatically
```

### 3. Start All Watchers (Persistent)

Using PM2 (recommended):

```bash
# Install PM2 if needed
npm install -g pm2

# Start all services
pm2 start gmail_watcher.py --interpreter python --name gmail-watcher
pm2 start linkedin_watcher.py --interpreter python --name linkedin-watcher
pm2 start orchestrator.py --interpreter python --name orchestrator
pm2 start email_reply_approver.py --interpreter python --name email-approver

# Save PM2 configuration (auto-restart on reboot)
pm2 save

# View status
pm2 status

# View logs
pm2 logs

# Stop all
pm2 stop all

# Delete all
pm2 delete all
```

### Alternative: Windows Task Scheduler

Create scheduled tasks for each watcher:

```powershell
# Gmail Watcher
schtasks /create /tn "GmailWatcher" /tr "python C:\path\to\gmail_watcher.py" /sc onstart /ru SYSTEM

# Orchestrator
schtasks /create /tn "Orchestrator" /tr "python C:\path\to\orchestrator.py" /sc onstart /ru SYSTEM
```

---

## Testing Workflow

### Test Email Processing

```bash
# 1. Send yourself an email marked "Important" in Gmail

# 2. Wait 2 minutes OR run manually
python gmail_watcher.py

# 3. Check for new file
dir Needs_Action\EMAIL_*.md

# 4. Run orchestrator to process
python orchestrator.py --mode=process-once

# 5. Copy the printed prompt → Paste to Qwen CLI

# 6. AI will create:
#    - Plans/Plan_EMAIL_*.md
#    - Pending_Approval/EMAIL_REPLY_*.md (if reply needed)

# 7. Review and approve reply (if created)
move Pending_Approval\EMAIL_REPLY_*.md Approved\

# 8. Email approver will log and move to Done/
python email_reply_approver.py
```

### Test LinkedIn Posting

```bash
# Check linkedin_poster.py configuration
# Run manually or wait for scheduled time
python linkedin_poster.py
```

---

## Commands Reference

### Watchers

| Command | Purpose |
|---------|---------|
| `python gmail_watcher.py` | Poll Gmail for important emails |
| `python linkedin_watcher.py` | Monitor LinkedIn messages |
| `python whatsapp_watcher.py` | Monitor WhatsApp messages |

### Orchestrator Modes

| Command | Purpose |
|---------|---------|
| `python orchestrator.py` | Watch mode (default) |
| `python orchestrator.py --mode=process-once` | Process all pending now |
| `python orchestrator.py --mode=daily-briefing` | Generate weekly briefing |

### Approvers

| Command | Purpose |
|---------|---------|
| `python email_reply_approver.py` | Process approved email replies |
| `python linkedin_approval_handler.py` | Process LinkedIn post approvals |

### PM2 Management

| Command | Purpose |
|---------|---------|
| `pm2 start <file> --interpreter python --name <name>` | Start service |
| `pm2 status` | View all services |
| `pm2 logs <name>` | View service logs |
| `pm2 stop <name>` | Stop service |
| `pm2 restart <name>` | Restart service |
| `pm2 delete <name>` | Remove service |
| `pm2 save` | Save for auto-restart |
| `pm2 startup` | Configure startup script |

---

## Logs Location

All logs are in `Logs/` directory:

| Log File | Source |
|----------|--------|
| `gmail_watcher.log` | Gmail polling |
| `linkedin_watcher.log` | LinkedIn monitoring |
| `whatsapp_watcher.log` | WhatsApp monitoring |
| `orchestrator.log` | Task processing |
| `email_reply_approver.log` | Email approval processing |
| `YYYY-MM-DD.md` | Daily activity logs |

---

## Configuration

### Gmail Query

Edit `gmail_watcher.py`:

```python
# Default: Important unread emails
GMAIL_QUERY = 'is:unread is:important'

# Alternative: All inbox emails
GMAIL_QUERY = 'is:unread in:inbox'

# Alternative: Specific sender
GMAIL_QUERY = 'is:unread from:boss@company.com'

# Alternative: Specific subjects
GMAIL_QUERY = 'is:unread subject:(urgent OR invoice)'
```

### Polling Interval

```python
POLL_INTERVAL = 120  # Seconds (default: 2 minutes)
```

### Priority Keywords

```python
urgent_keywords = ['urgent', 'asap', 'immediately', 'emergency']
invoice_keywords = ['invoice', 'payment', 'billing', 'receipt']
support_keywords = ['support', 'help', 'issue', 'problem', 'error']
```

---

## Troubleshooting

### Gmail Authentication Failed

```bash
# Delete old token and re-authenticate
del token.json
python gmail_watcher.py
```

### No Emails Found

1. Check email is marked "Important" in Gmail
2. Verify `credentials.json` has Gmail API enabled
3. Check query in `gmail_watcher.py`

### Orchestrator Not Processing

```bash
# Check logs
type Logs\orchestrator.log

# Run in process-once mode for debugging
python orchestrator.py --mode=process-once
```

### PM2 Not Starting

```bash
# Check PM2 installation
pm2 --version

# Reinstall if needed
npm install -g pm2

# Check Python path
where python
```

---

## Next Steps (Gold Tier)

- [ ] Add Calendar watcher
- [ ] Implement actual email sending (gmail.send scope)
- [ ] Add voice message processing
- [ ] Create web dashboard
- [ ] Add more AI skills
- [ ] Implement task prioritization
- [ ] Add notification system

---

*Silver Tier Complete - Ready for Hackathon Submission*
