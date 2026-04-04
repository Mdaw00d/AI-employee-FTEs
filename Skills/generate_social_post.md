# Skill: Generate Social Media Post

## Description
Create and publish posts to social media platforms (Facebook, Instagram, X/Twitter) using the social_poster.py tool.

## When to Use
- When a task requires posting content to social media
- When responding to social media inquiries with a public post
- When creating promotional or informational content
- After approval has been granted in Pending_Approval/

## Platform Capabilities

### Facebook
- Text posts up to 63,206 characters
- Image attachments supported
- Posts to user profile or page
- Uses persistent session: `./facebook_session`

### Instagram
- Requires image for posts
- Caption up to 2,200 characters
- Uses persistent session: `./instagram_session`

### X (Twitter)
- Text posts up to 280 characters (400 for Premium)
- Image attachments supported
- Uses persistent session: `./x_session`

## Usage

### Command Line
```bash
# Facebook post
python social_poster.py --platform facebook --text "Your post content here"

# Instagram post (requires image)
python social_poster.py --platform instagram --text "Caption here" --image path/to/image.jpg

# X (Twitter) post
python social_poster.py --platform x --text "Tweet content here"

# Dry run (test without posting)
python social_poster.py --platform facebook --text "Test post" --dry-run
```

### Parameters
| Parameter | Required | Description |
|-----------|----------|-------------|
| `--platform` | Yes | Platform: `facebook`, `instagram`, or `x` |
| `--text` | Yes | Content to post |
| `--image` | No | Path to image file (required for Instagram) |
| `--dry-run` | No | Test mode - shows what would be posted |

## Response Format

The tool returns JSON with the result:

```json
{
  "success": true,
  "platform": "facebook",
  "text": "Post content",
  "image": null,
  "message": "Post submitted successfully"
}
```

Or on error:

```json
{
  "success": false,
  "platform": "facebook",
  "error": "Error description"
}
```

## Workflow Integration

1. **Task Received**: Social media task in `Needs_Action/`
2. **Analysis**: Orchestrator creates prompt for AI
3. **Plan Created**: `Plans/Plan_SOCIAL_*.md` with strategy
4. **Approval**: If needed, create `Pending_Approval/SOCIAL_POST_*.md`
5. **Execution**: Call `generate_social_post()` skill
6. **Completion**: Move files to `Done/`, update Dashboard

## Example Task Flow

### Input (Needs_Action/FB_MESSAGE_20260305_143022.md)
```markdown
# Facebook Message - Needs Action

**Source:** Facebook Messenger
**Keywords:** sales, invoice
**Priority:** High

## Content
```
Hi, I'm interested in your services. Can you send me an invoice?
```
```

### AI Response Plan
```markdown
### Analysis
Customer inquiry with sales intent, requesting invoice.

### Classification
sales_lead

### Action Plan
1. Acknowledge the inquiry
2. Create social media post about our services
3. Follow up with direct message

### Post to Generate
Platform: facebook
Content: "We're excited to help new customers! Our team is ready to provide excellent service. DM us for inquiries!"
```

### Execution
```python
# After approval, execute:
python social_poster.py --platform facebook --text "We're excited to help new customers!..."
```

## Best Practices

1. **Always use dry-run first** to verify content
2. **Check character limits** for each platform
3. **Include relevant hashtags** when appropriate
4. **Review platform-specific guidelines**
5. **Ensure approval for sensitive content**
6. **Log all posts** in Daily Social Media Log

## Session Management

Each platform uses a persistent browser session:
- First run: Manual login required in browser window
- Subsequent runs: Session reused automatically
- Sessions stored in: `./facebook_session`, `./instagram_session`, `./x_session`

To reset a session, delete the corresponding directory.

## Error Handling

Common errors and solutions:

| Error | Solution |
|-------|----------|
| "Not logged in" | Login manually in the browser window |
| "Session expired" | Delete session folder and re-login |
| "Image required" | Provide --image parameter for Instagram |
| "Content too long" | Reduce text to platform limits |

## Logging

All posts are logged to `Logs/social_poster.log`:
- Timestamp
- Platform
- Content (truncated)
- Success/failure status

## Security Notes

- Never post sensitive information
- Never post financial data publicly
- Always use approval workflow for customer-facing content
- Sessions contain authentication tokens - protect the session directories
