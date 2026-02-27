# Skill: Process Email

**Name:** `process_email`
**Version:** 1.0
**Author:** AI Employee System
**Category:** Communication

---

## Description

This skill processes incoming emails that require action. It classifies emails by type, creates appropriate plan files, and drafts replies when needed.

---

## Trigger Conditions

This skill is automatically triggered when:

1. A new file appears in `Needs_Action/` with frontmatter containing:
   ```yaml
   type: email
   ```

2. The file has the naming pattern: `EMAIL_*_{timestamp}.md`

---

## Input Format

The skill expects a markdown file with YAML frontmatter:

```markdown
---
type: email
from: sender@example.com
subject: Email Subject Line
received: 2025-02-27 10:30:00
priority: high|medium|low
status: pending
message_id: gmail_message_id
to: recipient@example.com
---

# Email Requiring Action

## From
**Sender Name**

## Subject
Subject line

## Message
Email body/snippet content...

## Suggested Actions
- [ ] Reply
- [ ] Archive
- [ ] Flag
- [ ] Forward
```

---

## Processing Steps

### Step 1: Classify the Email

Analyze the email content and classify into one of these categories:

| Category | Description | Indicators |
|----------|-------------|------------|
| `sales` | Product/service inquiries | "pricing", "quote", "interested", "proposal" |
| `invoice` | Payment/billing related | "invoice", "payment", "receipt", "due" |
| `support` | Technical help requests | "issue", "problem", "error", "help" |
| `spam` | Promotional/unwanted | Unsolicited offers, suspicious links |
| `general` | Everything else | Networking, FYI, informational |

### Step 2: Create Plan File

Create a plan file in `Plans/` directory:

**Filename:** `Plans/Plan_EMAIL_{YYYYMMDD_HHMMSS}_{short_description}.md`

**Content Template:**
```markdown
---
type: plan
category: email_processing
classification: [sales|invoice|support|spam|general]
created: YYYY-MM-DD HH:MM:SS
priority: [high|medium|low]
status: in_progress
---

# Email Processing Plan

## Original Email
- **From:** sender@example.com
- **Subject:** Subject line
- **Received:** 2025-02-27 10:30:00

## Classification
[Classification with reasoning]

## Key Points
- [Point 1 from email]
- [Point 2 from email]

## Required Actions
- [ ] [Action item 1]
- [ ] [Action item 2]

## Timeline
[Any deadlines mentioned]

## Resources Needed
- [Any resources needed]

## Expected Outcome
[What success looks like]
```

### Step 3: Determine Reply Requirement

**Reply IS needed when:**
- Email asks a question
- Email requests action/response
- Email is from important contact (client, partner, manager)
- Email is sales/support inquiry

**Reply NOT needed when:**
- Email is spam/promotional
- Email is FYI only (no action required)
- Email is automated notification

### Step 4: Create Reply Draft (if needed)

If reply is needed, create draft in `Pending_Approval/`:

**Filename:** `Pending_Approval/EMAIL_REPLY_{YYYYMMDD_HHMM}.md`

**Content Template:**
```markdown
---
type: email_reply_draft
to: sender@example.com
subject: Re: Original Subject
original_message_id: gmail_message_id
classification: [classification]
priority: [priority]
created: YYYY-MM-DD HH:MM:SS
---

# Draft Email Reply

## To
sender@example.com

## Subject
Re: Original Subject

## Body

Dear [Name],

[Professional response addressing the email content]

Best regards,
[Your name]

---
**Note:** This draft requires human approval before sending.
Move this file to Approved/ to authorize sending.
```

### Step 5: Complete Processing

1. Move original email file from `Needs_Action/` to `Done/`
2. Update `Dashboard.md` with completion entry
3. Log processing details to `Logs/orchestrator.log`

---

## Output Files

| File | Location | Purpose |
|------|----------|---------|
| Plan | `Plans/Plan_EMAIL_*.md` | Documents classification and actions |
| Reply Draft | `Pending_Approval/EMAIL_REPLY_*.md` | Draft awaiting approval |
| Completed | `Done/EMAIL_*.md` | Archived original email |

---

## Approval Workflow

```
Needs_Action/ → [Orchestrator] → Plans/ + Pending_Approval/
                                              ↓
                                    [Human Review]
                                              ↓
                                    Approved/ → [Approver] → Done/
```

1. AI creates draft in `Pending_Approval/`
2. Human reviews draft content
3. Human moves file to `Approved/` to authorize
4. `email_reply_approver.py` processes and logs (future: sends via Gmail API)
5. File moved to `Done/`

---

## Error Handling

| Error | Action |
|-------|--------|
| Missing frontmatter | Log warning, skip file |
| Invalid email format | Create plan noting parsing error |
| Gmail API failure | Retry with exponential backoff |
| Duplicate processing | Check `processed_ids.pkl` before processing |

---

## Configuration

Edit `gmail_watcher.py` to customize:

```python
# Change email query
GMAIL_QUERY = 'is:unread is:important'  # Default
GMAIL_QUERY = 'is:unread in:inbox'      # All inbox emails
GMAIL_QUERY = 'is:unread from:boss@company.com'  # Specific sender

# Change polling interval
POLL_INTERVAL = 120  # Seconds (default: 2 minutes)

# Change priority keywords
urgent_keywords = ['urgent', 'asap', 'immediately']
invoice_keywords = ['invoice', 'payment', 'billing']
support_keywords = ['support', 'help', 'issue']
```

---

## Testing

1. Send yourself an email marked as "Important" in Gmail
2. Wait for Gmail watcher to poll (or run manually)
3. Check `Needs_Action/` for new `EMAIL_*.md` file
4. Run orchestrator: `python orchestrator.py --mode=process-once`
5. Review generated prompt and plan file
6. If reply draft created, review and move to `Approved/`
7. Run approver: `python email_reply_approver.py`

---

## Related Skills

- `process_task` - General task processing
- `linkedin_sales_post` - LinkedIn content posting

---

## Future Enhancements

- [ ] Actual email sending via Gmail API (requires `gmail.send` scope)
- [ ] Attachment handling
- [ ] Email threading/conversation tracking
- [ ] Smart reply suggestions using AI
- [ ] Email priority scoring based on sender importance

---

*Generated by AI Employee System - Silver Tier*
