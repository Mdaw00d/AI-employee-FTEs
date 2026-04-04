# Gold Tier Architecture

## System Overview

The Gold Tier extends the AI Employee system with comprehensive social media monitoring, multi-step task processing, and enhanced automation capabilities.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GOLD TIER ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PERCEPTION LAYER (Watchers)                       │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  Facebook    │  │  Instagram   │  │  X (Twitter) │               │   │
│  │  │  Watcher     │  │  Watcher     │  │  Watcher     │               │   │
│  │  │  (60s poll)  │  │  (60s poll)  │  │  (60s poll)  │               │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │   │
│  │         │                 │                 │                        │   │
│  │         ▼                 ▼                 ▼                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │              Needs_Action/ Directory (Input Queue)           │     │   │
│  │  │  FB_*.md │ IG_*.md │ X_*.md │ EMAIL_*.md │ TASK_*.md        │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   REASONING LAYER (AI Processing)                    │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │                    Orchestrator                              │     │   │
│  │  │  ┌──────────────────────────────────────────────────────┐   │     │   │
│  │  │  │  Ralph Wiggum Loop Controller (Gold Tier)            │   │     │   │
│  │  │  │  - Iterative AI calls (max 10)                       │   │     │   │
│  │  │  │  - Continuation until <TASK_COMPLETE>                │   │     │   │
│  │  │  │  - Context accumulation across iterations            │   │     │   │
│  │  │  └──────────────────────────────────────────────────────┘   │     │   │
│  │  │                                                              │     │   │
│  │  │  ┌──────────────────────────────────────────────────────┐   │     │   │
│  │  │  │  Qwen AI / OpenAI Compatible API                      │   │     │   │
│  │  │  │  - Task classification                                │   │     │   │
│  │  │  │  - Response generation                                │   │     │   │
│  │  │  │  - Plan creation                                      │   │     │   │
│  │  │  └──────────────────────────────────────────────────────┘   │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │  Plans/ Directory (Multi-step task plans)                    │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    ACTION LAYER (Execution)                          │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │  Pending_Approval/ → Approved/ → Execution                   │    │   │
│  │  │  (Human review gate for sensitive actions)                   │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                              │                                        │   │
│  │                              ▼                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │              MCP Servers (Model Context Protocol)            │    │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │    │   │
│  │  │  │  Email   │ │  Social  │ │  Browser │ │  Odoo    │       │    │   │
│  │  │  │  :8000   │ │  :8001   │ │  :8002   │ │  :8070   │       │    │   │
│  │  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │    │   │
│  │  │       │            │            │            │              │    │   │
│  │  │       ▼            ▼            ▼            ▼              │    │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │    │   │
│  │  │  │  Gmail   │ │  FB/IG/X │ │  Chrome  │ │  ERP/    │       │    │   │
│  │  │  │  API     │ │  Posts   │ │  Control │ │  Finance │       │    │   │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      OUTPUT / COMPLETION                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  Done/       │  │  Dashboard   │  │  Logs/       │               │   │
│  │  │  (Archive)   │  │  (Status)    │  │  (Audit)     │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Perception Layer (Watchers)

| Component | File | Poll Interval | Output | Session |
|-----------|------|---------------|--------|---------|
| Facebook Watcher | `facebook_watcher.py` | 60s | `Needs_Action/FB_*.md` | `./facebook_session` |
| Instagram Watcher | `instagram_watcher.py` | 60s | `Needs_Action/IG_*.md` | `./instagram_session` |
| X (Twitter) Watcher | `x_watcher.py` | 60s | `Needs_Action/X_*.md` | `./x_session` |
| Gmail Watcher | `gmail_watcher.py` | 60s | `Needs_Action/EMAIL_*.md` | OAuth |

**Keywords Monitored:**
- High Priority: `urgent`, `invoice`, `payment`, `complaint`
- Medium Priority: `sales`, `order`, `customer`, `review`
- Low Priority: `dm`, `collab`, `general`

### Reasoning Layer (AI Processing)

#### Orchestrator
- **File:** `orchestrator.py`
- **Role:** Central brain, monitors `Needs_Action/`, routes tasks
- **Modes:** `normal`, `daily-briefing`, `weekly-audit`, `loop`

#### Ralph Wiggum Loop Controller (Gold Tier)
- **File:** `ralph_wiggum.py`
- **Role:** Iterative AI processing for complex multi-step tasks
- **Features:**
  - Loops until `<TASK_COMPLETE>` marker or file in `Done/`
  - Max iterations: 10 (configurable)
  - Accumulates context across iterations
  - Logs to `Logs/ralph_loop.log`

#### AI Backend
- **Primary:** Qwen API (`qwen-plus`)
- **Fallback:** OpenAI-compatible endpoints
- **Configuration:** `OPENAI_API_BASE`, `OPENAI_API_KEY`

### Action Layer (Execution)

#### MCP Servers (Model Context Protocol)

| Server | Port | Methods | Purpose |
|--------|------|---------|---------|
| Email MCP | 8000 | `send_email`, `create_draft`, `send_reply` | Gmail integration |
| Social MCP | 8001 | `post_facebook`, `post_instagram`, `post_x` | Social media posting |
| Browser MCP | 8002 | `navigate`, `fill`, `click`, `screenshot` | Browser automation |
| Odoo MCP | 8070 | `create_invoice`, `get_transactions`, `register_payment` | ERP/Finance |

#### Skills System
Skills are reusable action modules that can be called by the AI:

```
┌─────────────────────────────────────────────────────┐
│                  Skills Library                      │
├─────────────────────────────────────────────────────┤
│  generate_social_post(platform, text, image)        │
│  send_email(recipient, subject, body)               │
│  create_invoice(partner, amount, description)       │
│  navigate_browser(url, action)                      │
│  process_payment(invoice_id, method)                │
└─────────────────────────────────────────────────────┘
```

### Approval Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Pending_       │────▶│  Human Review   │────▶│  Approved/      │
│  Approval/      │     │  (Manual)       │     │  (Ready to exec)│
│  Draft responses│     │  - Check content│     │                 │
│  - Social posts │     │  - Verify data  │     │                 │
│  - Email drafts │     │  - Move to Approved│   │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  MCP Execution  │
                                                │  (Automated)    │
                                                └────────┬────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │  Done/          │
                                                │  (Archive)      │
                                                └─────────────────┘
```

## Data Flow

### 1. Task Ingestion (Perception)
```
Social Media Platform → Browser Watcher → Keyword Match → Needs_Action/*.md
```

### 2. Task Processing (Reasoning)
```
Needs_Action/*.md → Orchestrator → Ralph Loop → AI Processing → Plans/*.md
```

### 3. Action Execution (Action)
```
Plans/*.md → Pending_Approval/*.md → Human Review → Approved/*.md → MCP → Done/
```

## File Structure

```
bronze-tier/
├── # Core Components
├── orchestrator.py           # Central brain
├── ralph_wiggum.py           # Loop controller (Gold Tier)
│
├── # Watchers (Perception)
├── facebook_watcher.py
├── instagram_watcher.py
├── x_watcher.py
├── gmail_watcher.py
│
├── # MCP Servers (Action)
├── email_mcp.py
├── social_mcp.py
├── browser_mcp.py
├── odoo_mcp.py
│
├── # Skills
├── social_poster.py
├── social_summary.py
├── email_reply_approver.py
│
├── # Directories
├── Needs_Action/             # Input queue (FB_*, IG_*, X_*, EMAIL_*)
├── Plans/                    # Multi-step task plans
├── Pending_Approval/         # Awaiting human review
├── Approved/                 # Ready for execution
├── Done/                     # Completed tasks
├── Logs/                     # Audit logs
│   ├── orchestrator.log
│   ├── ralph_loop.log
│   ├── facebook_watcher.log
│   └── ...
└── Briefings/                # Generated reports
```

## Configuration

### Environment Variables
```bash
# AI Configuration
OPENAI_API_BASE=http://localhost:8000/v1
OPENAI_API_KEY=your-api-key
QWEN_API_URL=https://dashscope.aliyuncs.com/api/v1

# DRY_RUN=true  # Print prompts without execution
```

### MCP Server Configuration
```python
MCP_SERVERS = {
    'email': {'host': 'localhost', 'port': 8000, 'url': 'http://localhost:8000/rpc'},
    'social': {'host': 'localhost', 'port': 8001, 'url': 'http://localhost:8001/rpc'},
    'browser': {'host': 'localhost', 'port': 8002, 'url': 'http://localhost:8002/rpc'},
    'odoo': {'host': 'localhost', 'port': 8070, 'url': 'http://localhost:8070/rpc'},
}
```

## Startup Sequence

```bash
# Terminal 1: Start MCP Servers
python email_mcp.py &
python social_mcp.py &
python browser_mcp.py &
python odoo_mcp.py &

# Terminal 2: Start Watchers
python facebook_watcher.py &
python instagram_watcher.py &
python gmail_watcher.py &

# Terminal 3: Start Orchestrator (with loop mode)
python orchestrator.py --mode=loop
```

## Security Considerations

1. **Session Storage:** Browser sessions stored locally, never commit to version control
2. **Approval Gate:** All external communications require human approval
3. **Financial Actions:** Invoice/payment actions blocked without explicit approval
4. **API Keys:** Use environment variables, never hardcode
5. **Rate Limiting:** 60s poll intervals to avoid platform throttling

## Extensibility

### Adding New Watchers
1. Create `newplatform_watcher.py` following existing watcher pattern
2. Define keywords and output format (`NP_*.md`)
3. Update orchestrator to recognize new file prefix

### Adding New MCP Servers
1. Create `newplatform_mcp.py` with JSON-RPC interface
2. Define methods following MCP convention
3. Add to `MCP_SERVERS` dict in orchestrator

### Adding New Skills
1. Create skill function with clear input/output
2. Register in skill library
3. Document in AI system prompt

## Performance Characteristics

| Component | Latency | Throughput |
|-----------|---------|------------|
| Watchers (poll) | 60s | 1 check/min |
| AI Processing | 2-10s | 6-30 tasks/min |
| Ralph Loop | 20-100s | 1-5 complex tasks/min |
| MCP Execution | 1-5s | 12-60 actions/min |

## Monitoring & Observability

- **Dashboard.md:** Real-time system status
- **Logs/*.log:** Component-specific activity logs
- **ralph_loop.log:** Iteration tracking for complex tasks
- **Briefings/:** Generated summaries (daily/weekly)
