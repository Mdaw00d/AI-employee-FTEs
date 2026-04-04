# Gold Tier Social Media Integration

## Overview

The Gold Tier adds comprehensive social media monitoring and posting capabilities for Facebook, Instagram, and X (Twitter).

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Facebook       │────▶│ facebook_       │────▶│  Needs_Action/  │
│  Messenger      │     │ watcher.py      │     │  FB_*.md        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Instagram      │────▶│ instagram_      │────▶│  Needs_Action/  │
│  DMs            │     │ watcher.py      │     │  IG_*.md        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  X (Twitter)    │────▶│ x_              │────▶│  Needs_Action/  │
│  Mentions/DMs   │     │ watcher.py      │     │  X_*.md         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Orchestrator   │
                                                │  (AI Processing)│
                                                └─────────────────┘
                                                        │
                        ┌─────────────────┐             │
                        │  social_        │◀────────────┘
                        │  poster.py      │
                        └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │  Facebook       │
                        │  Instagram      │
                        │  X (Twitter)    │
                        └─────────────────┘
```

## Components

### 1. Facebook Watcher (`facebook_watcher.py`)
- **Purpose**: Monitor Facebook messages and notifications
- **Session**: `./facebook_session` (persistent browser session)
- **Keywords**: urgent, invoice, sales, payment, order, customer, complaint, review
- **Output**: `Needs_Action/FB_*.md` files
- **Poll Interval**: 60 seconds

**Run:**
```bash
python facebook_watcher.py
```

### 2. Instagram Watcher (`instagram_watcher.py`)
- **Purpose**: Monitor Instagram DMs and notifications
- **Session**: `./instagram_session` (persistent browser session)
- **Keywords**: urgent, invoice, sales, payment, order, customer, complaint, review, dm, collab
- **Output**: `Needs_Action/IG_*.md` files
- **Poll Interval**: 60 seconds

**Run:**
```bash
python instagram_watcher.py
```

### 3. Social Media Poster (`social_poster.py`)
- **Purpose**: Post content to Facebook, Instagram, or X
- **Platforms**: facebook, instagram, x
- **Features**: Dry-run mode, image support
- **Logs**: `Logs/social_poster.log`

**Run:**
```bash
# Facebook post
python social_poster.py --platform facebook --text "Hello World"

# Instagram post (requires image)
python social_poster.py --platform instagram --text "Caption" --image photo.jpg

# X (Twitter) post
python social_poster.py --platform x --text "Tweet content"

# Dry run (test)
python social_poster.py --platform facebook --text "Test" --dry-run
```

### 4. Social Media Summary (`social_summary.py`)
- **Purpose**: Generate summaries of recent activity
- **Output**: `Briefings/{platform}_summary_*.md`
- **Logs**: `Logs/social_summary.log`

**Run:**
```bash
# Single platform
python social_summary.py --platform facebook

# All platforms
python social_summary.py --all
```

### 5. Orchestrator (`orchestrator.py`)
- **Purpose**: Central task processing with social media support
- **Monitors**: `Needs_Action/` including FB_*, IG_*, X_* files
- **Approval**: Creates `Pending_Approval/` files for actions
- **Execution**: Calls `social_poster.py` after approval

**Run:**
```bash
python orchestrator.py
```

## File Structure

```
bronze-tier/
├── facebook_watcher.py       # Facebook monitor
├── instagram_watcher.py      # Instagram monitor
├── social_poster.py          # Multi-platform poster
├── social_summary.py         # Summary generator
├── orchestrator.py           # Central orchestrator (updated)
├── start_social_watchers.bat # Startup script
├── GOLD_TIER_README.md       # This file
│
├── facebook_session/         # FB browser session (auto-created)
├── instagram_session/        # IG browser session (auto-created)
├── x_session/                # X browser session (auto-created)
│
├── Needs_Action/
│   ├── FB_message_*.md      # Facebook alerts
│   ├── FB_notification_*.md
│   ├── IG_dm_*.md           # Instagram alerts
│   └── IG_notification_*.md
│
├── Pending_Approval/
│   ├── SOCIAL_REPLY_*.md    # Draft responses
│   └── SOCIAL_POST_*.md     # Posts awaiting approval
│
├── Approved/
│   └── *.md                 # Approved actions ready for execution
│
├── Briefings/
│   ├── facebook_summary_*.md
│   ├── instagram_summary_*.md
│   └── x_summary_*.md
│
└── Logs/
    ├── facebook_watcher.log
    ├── instagram_watcher.log
    ├── social_poster.log
    ├── social_summary.log
    └── orchestrator.log
```

## Quick Start

### 1. Install Dependencies
```bash
pip install playwright
playwright install chromium
```

### 2. Start All Services
```bash
start_social_watchers.bat
```

Or start individually:
```bash
# Terminal 1: Facebook Watcher
python facebook_watcher.py

# Terminal 2: Instagram Watcher
python instagram_watcher.py

# Terminal 3: Orchestrator
python orchestrator.py
```

### 3. First-Time Login
- Browser windows will open for Facebook and Instagram
- Log in manually to each platform
- Sessions are saved for future runs

### 4. Generate Summary (Optional)
```bash
python social_summary.py --all
```

## Workflow Example

### Processing a Facebook Message

1. **Watcher Detects Message**
   ```
   facebook_watcher.py detects: "Hi, I need an invoice"
   Keyword matched: "invoice"
   ```

2. **Action File Created**
   ```
   Needs_Action/FB_MESSAGE_20260305_143022.md
   ```

3. **Orchestrator Processes**
   ```
   - Reads FB_MESSAGE_*.md
   - Generates AI prompt
   - Creates plan: Plans/Plan_SOCIAL_invoice.md
   - Creates approval: Pending_Approval/SOCIAL_REPLY_*.md
   ```

4. **Human Reviews Approval**
   ```
   - Review draft response in Pending_Approval/
   - If approved, move to Approved/
   ```

5. **Orchestrator Executes**
   ```
   - Detects file in Approved/
   - Calls social_poster.py
   - Posts to Facebook
   - Moves files to Done/
   ```

## Keyword Detection

Default keywords that trigger action files:

| Keyword | Priority | Action |
|---------|----------|--------|
| urgent | High | Immediate attention |
| invoice | High | Financial action |
| sales | Medium | Sales lead |
| payment | High | Financial action |
| order | Medium | Order processing |
| customer | Medium | Customer service |
| complaint | High | Support needed |
| review | Medium | Reputation mgmt |
| collab | Medium | Partnership (IG) |
| dm | Low | General message (IG) |

## Configuration

Edit the Python files to customize:

```python
# In facebook_watcher.py or instagram_watcher.py
POLL_INTERVAL = 60  # Seconds between checks
KEYWORDS = ["urgent", "invoice", "sales", ...]  # Keywords to monitor
```

```python
# In social_poster.py
PLATFORMS = {
    'facebook': {'url': 'https://www.facebook.com', ...},
    'instagram': {'url': 'https://www.instagram.com', ...},
    'x': {'url': 'https://twitter.com', ...}
}
```

## Troubleshooting

### "Not logged in" Error
- Open the browser window that appeared
- Log in manually
- Session will be saved for next run

### Session Issues
```bash
# Delete session and re-login
rmdir /s /q facebook_session
rmdir /s /q instagram_session
rmdir /s /q x_session

# Restart watchers
python facebook_watcher.py
```

### Playwright Errors
```bash
# Reinstall Playwright
pip uninstall playwright
pip install playwright
playwright install chromium
```

### Posts Not Appearing
- Check `Logs/social_poster.log` for errors
- Ensure browser session is valid
- Try dry-run first: `--dry-run`

## Security Notes

1. **Session Protection**: Session directories contain authentication tokens
   - Do not share session folders
   - Do not commit to version control

2. **Approval Workflow**: Always use approval for:
   - Customer-facing posts
   - Financial information
   - Sensitive responses

3. **Rate Limiting**: Platforms may block automated access
   - Use reasonable poll intervals (60s+)
   - Don't post too frequently

## API Integration (Future)

For production use, consider official APIs:
- **Facebook**: Meta Graph API
- **Instagram**: Instagram Basic Display API
- **X**: Twitter API v2

Current implementation uses browser automation for simplicity and to avoid API key management.

## Logs

All activity is logged:

| Log File | Contents |
|----------|----------|
| `facebook_watcher.log` | FB monitoring activity |
| `instagram_watcher.log` | IG monitoring activity |
| `social_poster.log` | Post creation/submission |
| `social_summary.log` | Summary generation |
| `orchestrator.log` | Task processing |

## Support

For issues or questions:
1. Check logs in `Logs/` directory
2. Review this documentation
3. Check Playwright documentation: https://playwright.dev/python
