# Gold Tier Social Media - Quick Reference

## Run Commands

### Start All Services
```bash
start_social_watchers.bat
```

### Start Individual Services
```bash
# Facebook Watcher (monitor messages/notifications)
python facebook_watcher.py

# Instagram Watcher (monitor DMs/notifications)
python instagram_watcher.py

# X (Twitter) Watcher (monitor mentions/DMs)
python x_watcher.py

# Orchestrator (process tasks)
python orchestrator.py

# Summary Generator (on-demand)
python social_summary.py --all
python social_summary.py --platform facebook
python social_summary.py --platform x
```

### Post to Social Media
```bash
# Facebook
python social_poster.py --platform facebook --text "Your post"

# Instagram (requires image)
python social_poster.py --platform instagram --text "Caption" --image photo.jpg

# X (Twitter)
python social_poster.py --platform x --text "Tweet"

# Test mode (dry-run)
python social_poster.py --platform facebook --text "Test" --dry-run
```

## File Patterns

| Pattern | Description | Action |
|---------|-------------|--------|
| `FB_MESSAGE_*.md` | Facebook message | AI processes, may reply |
| `FB_NOTIFICATION_*.md` | Facebook notification | AI processes |
| `IG_DM_*.md` | Instagram DM | AI processes, may reply |
| `IG_NOTIFICATION_*.md` | Instagram notification | AI processes |
| `X_MENTION_*.md` | X (Twitter) mention | AI processes, may reply |
| `X_DM_*.md` | X (Twitter) DM | AI processes, may reply |
| `X_NOTIFICATION_*.md` | X notification | AI processes |
| `SOCIAL_REPLY_*.md` | Draft response | Move to Approved/ to send |
| `SOCIAL_POST_*.md` | Draft post | Move to Approved/ to publish |

## Keywords Monitored

**High Priority:** urgent, invoice, payment, complaint, help, support
**Medium Priority:** sales, order, customer, review, collab
**Low Priority:** dm

## Directory Structure

```
Needs_Action/          ← New tasks appear here (FB_*, IG_*, X_*)
Pending_Approval/      ← Drafts awaiting approval
Approved/              ← Approved actions (auto-executed)
Done/                  ← Completed tasks
Briefings/             ← Platform summaries (facebook_*, instagram_*, x_*)
Logs/                  ← All log files
```

## Workflow

1. **Watcher detects** keyword in message/notification/mention
2. **Creates file** in Needs_Action/ (FB_*.md, IG_*.md, or X_*.md)
3. **Orchestrator processes** file, creates AI prompt
4. **AI creates plan** and draft response in Pending_Approval/
5. **Human reviews** and moves to Approved/ if OK
6. **Orchestrator executes** post/reply via social_poster.py
7. **Files moved** to Done/, Dashboard updated

## Logs

| Log File | Purpose |
|----------|---------|
| Logs/facebook_watcher.log | FB monitoring |
| Logs/instagram_watcher.log | IG monitoring |
| Logs/x_watcher.log | X monitoring |
| Logs/social_poster.log | Post execution |
| Logs/social_summary.log | Summary generation |
| Logs/orchestrator.log | Task processing |

## Troubleshooting

**Not logged in?** → Login in browser window, session saved automatically
**Session expired?** → Delete `facebook_session/`, `instagram_session/`, or `x_session/` folder and re-login
**Posts failing?** → Check logs, try `--dry-run` first
**Syntax errors?** → All files verified with `python -m py_compile`

## Configuration

Edit these values in the Python files:

```python
# Watchers (facebook_watcher.py, instagram_watcher.py, x_watcher.py)
POLL_INTERVAL = 60  # Seconds between checks
KEYWORDS = ["urgent", "invoice", "sales", ...]

# Poster (social_poster.py)
# Platform URLs and selectors in PLATFORMS dict
```

## Tips

1. **First run**: Browser windows open for login - sessions persist
2. **Dry-run**: Always test posts with `--dry-run` before real posting
3. **Approval**: Never skip approval workflow for customer-facing content
4. **Monitoring**: Check Logs/ directory for issues
5. **Summaries**: Run `social_summary.py --all` daily for overview
6. **X Character Limit**: Keep responses under 280 characters
