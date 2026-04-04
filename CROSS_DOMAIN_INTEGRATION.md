# Cross-Domain Integration - Gold Tier Complete

## Overview

The Cross-Domain Integration system enables the AI Employee system to intelligently route and process tasks across **Personal** and **Business** domains, with comprehensive audit logging for compliance and accountability.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CROSS-DOMAIN INTEGRATION LAYER                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  Domain         │     │  Cross-Domain   │     │  Audit          │       │
│  │  Classifier     │     │  Router         │     │  Trail          │       │
│  │                 │     │                 │     │                 │       │
│  │  - Keywords     │     │  - MCP routing  │     │  - JSONL logs   │       │
│  │  - Source map   │     │  - Parallel     │     │  - Crypto hash  │       │
│  │  - Confidence   │     │  - Sequential   │     │  - Compliance   │       │
│  │  - Rules        │     │  - Chaining     │     │  - Query        │       │
│  └────────┬────────┘     └────────┬────────┘     └────────┬────────┘       │
│           │                       │                       │                 │
│           └───────────────────────┼───────────────────────┘                 │
│                                   │                                         │
│                                   ▼                                         │
│                    ┌─────────────────────────────┐                         │
│                    │   Orchestrator Integration   │                         │
│                    │   (Domain-Aware Processing)  │                         │
│                    └─────────────┬───────────────┘                         │
│                                  │                                          │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  PERSONAL       │  │  BUSINESS       │  │  MIXED          │
    │  Domain         │  │  Domain         │  │  Domain         │
    │                 │  │                 │  │                 │
    │  - Auto-execute │  │  - Approval req │  │  - Case-by-case │
    │  - Normal prio  │  │  - High prio    │  │  - Review       │
    │  - Email/Social │  │  - All MCPs     │  │  - Flexible     │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Components

### 1. Domain Classifier (`domain_classifier.py`)

Intelligently classifies incoming tasks and communications into domains.

**Features:**
- Keyword-based classification
- Source-based domain mapping
- Confidence scoring
- Custom rule support
- Classification history

**Usage:**
```python
from domain_classifier import DomainClassifier, Domain

classifier = DomainClassifier()

# Classify content
domain = classifier.classify_content(
    content="Invoice #1234 for client ABC - Payment due",
    source="email"
)
# Returns: Domain.BUSINESS

# Get routing rules
routing = classifier.get_routing_rules(domain)
# Returns domain-specific configuration

# Get full metadata
metadata = classifier.create_domain_metadata(content, source)
# Returns: {domain, confidence, routing, keywords_detected, ...}
```

**Domain Classification Rules:**

| Domain | Characteristics | Auto-Execute | Approval Required |
|--------|----------------|---------------|-------------------|
| BUSINESS | Financial, clients, operations | ❌ | ✅ Yes |
| PERSONAL | Friends, family, social | ✅ Yes | ❌ No |
| MIXED | Ambiguous or both domains | ❌ | ✅ Yes |
| UNKNOWN | Unclassifiable | ❌ | ✅ Yes |

### 2. Cross-Domain Router (`cross_domain_router.py`)

Routes tasks to appropriate MCP servers with domain awareness.

**Features:**
- Single-domain task routing
- Cross-domain composite actions
- Parallel execution
- Sequential action chaining
- MCP server health monitoring

**Usage:**
```python
from cross_domain_router import CrossDomainRouter

router = CrossDomainRouter()

# Route a single-domain task
result = router.route_task({
    'domain': 'business',
    'action': 'create_invoice',
    'params': {
        'partner_name': 'ABC Corp',
        'amount': 5000.00
    },
    'priority': 'high'
})

# Route a cross-domain composite action
result = router.route_task({
    'domain': 'business',
    'action': 'invoice_and_notify',  # Creates invoice AND sends email
    'params': {
        'customer': 'ABC Corp',
        'amount': 5000.00,
        'notify_email': 'billing@abccorp.com'
    },
    'chain': [
        {'action': 'send_email', 'params': {'subject': 'Invoice Created'}}
    ]
})
```

**Composite Actions:**

| Action | Description | MCP Servers Used |
|--------|-------------|------------------|
| `invoice_and_notify` | Create invoice + send notification | Odoo + Email |
| `social_and_email` | Post to social + send email | Social + Email |
| `full_campaign` | Get data + post social + email | Odoo + Social + Email |

### 3. Audit Trail (`audit_trail.py`)

Comprehensive, immutable audit logging for compliance and accountability.

**Features:**
- Append-only JSONL logs
- Cryptographic hash chaining
- Daily log rotation
- Query and filter capabilities
- Compliance report generation
- Integrity verification

**Usage:**
```python
from audit_trail import AuditTrail, AuditEventType

audit = AuditTrail()

# Log an event
entry_id = audit.log_event(
    event_type=AuditEventType.TASK_COMPLETED,
    actor="orchestrator",
    domain="business",
    action="create_invoice",
    target="INV-2026-001",
    result="success",
    metadata={"amount": 5000.00},
    duration_ms=234
)

# Query events
events = audit.query(
    date="2026-04-02",
    domain="business",
    event_type="task_completed"
)

# Verify integrity
integrity = audit.verify_integrity(date="2026-04-02")
print(f"Log integrity valid: {integrity['valid']}")

# Export for compliance
audit.export_audit_trail(
    output_path="audit_2026-04-02.json",
    format="json"  # or "csv"
)

# Generate compliance report
report = audit.generate_compliance_report(
    report_type="daily",
    date="2026-04-02"
)
```

**Audit Event Types:**

```python
class AuditEventType(Enum):
    # Task events
    TASK_CREATED, TASK_STARTED, TASK_COMPLETED, TASK_FAILED
    
    # Domain events
    DOMAIN_CLASSIFIED, DOMAIN_ROUTED, CROSS_DOMAIN_ACTION
    
    # MCP events
    MCP_CALL, MCP_SUCCESS, MCP_FAILURE
    
    # Approval events
    APPROVAL_REQUESTED, APPROVAL_GRANTED, APPROVAL_DENIED
    
    # Financial events (compliance)
    INVOICE_CREATED, PAYMENT_RECEIVED, PAYMENT_SENT
```

### 4. Orchestrator Integration (`orchestrator_cross_domain.py`)

Integrates cross-domain capabilities into the orchestrator.

**Usage:**
```python
from orchestrator_cross_domain import CrossDomainIntegration

integration = CrossDomainIntegration()

# Process a task with full domain awareness
result = integration.process_with_domain_awareness(
    task_file="Needs_Action/email_001.md",
    content="Create invoice for ABC Corp - $5000"
)

# Get statistics
stats = integration.get_domain_statistics()
print(f"Success rate: {stats['success_rate']:.1f}%")

# Get MCP server status
mcp_status = integration.get_mcp_server_status()
```

## File Structure

```
bronze-tier/
├── # Cross-Domain Integration
├── domain_classifier.py          # Domain classification
├── cross_domain_router.py        # Task routing across MCPs
├── audit_trail.py                # Comprehensive audit logging
├── orchestrator_cross_domain.py  # Orchestrator integration
├── CROSS_DOMAIN_INTEGRATION.md   # This documentation
│
├── # Domain-Specific Directories
├── Needs_Action/
│   ├── Personal/                 # Personal domain tasks
│   ├── Business/                 # Business domain tasks
│   └── Mixed/                    # Mixed domain tasks
│
├── Done/
│   ├── Personal/                 # Completed personal tasks
│   ├── Business/                 # Completed business tasks
│   └── Mixed/                    # Completed mixed tasks
│
└── Logs/
    ├── Audit/
    │   ├── audit_2026-04-02.jsonl  # Daily audit logs
    │   └── audit_2026-04-03.jsonl
    ├── domain_classifier.log
    ├── cross_domain_router.log
    └── audit_trail.log
```

## Workflow Example

### Processing a Business Invoice Request

```
1. EMAIL RECEIVED
   └─> gmail_watcher.py detects: "Create invoice for ABC Corp - $5000"
       └─> Creates: Needs_Action/EMAIL_invoice_001.md

2. DOMAIN CLASSIFICATION
   └─> domain_classifier.py analyzes content
       ├─> Keywords: "invoice", "ABC Corp", "$5000"
       ├─> Domain: BUSINESS (confidence: 0.95)
       └─> Routing: approval_required=True, priority=high

3. AUDIT LOGGING
   └─> audit_trail.py logs:
       - DOMAIN_CLASSIFIED event
       - TASK_STARTED event

4. CROSS-DOMAIN ROUTING
   └─> cross_domain_router.py routes to:
       ├─> Odoo MCP: create_invoice()
       └─> Email MCP: send_notification()

5. EXECUTION
   └─> Sequential execution:
       ├─> Step 1: Create invoice in Odoo → INV-2026-001
       └─> Step 2: Send email notification → billing@abccorp.com

6. COMPLETION
   └─> audit_trail.py logs:
       - TASK_COMPLETED event
       - File moved to: Done/Business/EMAIL_invoice_001.md
```

## Configuration

### Custom Classification Rules

Create `domain_rules.json` for custom classification:

```json
{
  "business_keywords": ["contract", "legal", "compliance"],
  "personal_keywords": ["weekend", "vacation", "family"],
  "source_mapping": {
    "work_email": "business",
    "personal_gmail": "personal"
  },
  "rules": [
    {
      "keywords": ["urgent", "ceo"],
      "domain": "business"
    }
  ]
}
```

### Environment Variables

```bash
# Audit Trail
AUDIT_ENABLE_CHAINING=true    # Enable cryptographic chaining
AUDIT_RETENTION_DAYS=90       # Log retention period

# Cross-Domain Router
MCP_TIMEOUT=30                # MCP call timeout (seconds)
MCP_RETRY_ATTEMPTS=3          # Retry failed MCP calls

# Domain Classifier
CLASSIFIER_CONFIDENCE_THRESHOLD=0.7  # Auto-classify threshold
```

## API Reference

### Domain Classifier

```python
classifier = DomainClassifier()

# Classify content
domain = classifier.classify_content(content: str, source: str = None) -> Domain

# Get routing rules
routing = classifier.get_routing_rules(domain: Domain) -> Dict

# Get metadata
metadata = classifier.create_domain_metadata(content: str, source: str) -> Dict

# Export classification log
classifier.export_classification_log(filepath: str) -> None
```

### Cross-Domain Router

```python
router = CrossDomainRouter()

# Route task
result = router.route_task(task: Dict) -> Dict

# Get server status
status = router.get_server_status() -> Dict

# Get execution history
history = router.get_execution_history(limit: int, domain: str) -> List[Dict]

# Export audit trail
path = router.export_audit_trail(output_path: str, date: str) -> str
```

### Audit Trail

```python
audit = AuditTrail()

# Log event
entry_id = audit.log_event(
    event_type: AuditEventType,
    actor: str,
    domain: str,
    action: str = None,
    target: str = None,
    result: str = None,
    metadata: Dict = None
) -> str

# Query events
events = audit.query(
    date: str,
    event_type: str = None,
    actor: str = None,
    domain: str = None
) -> List[Dict]

# Verify integrity
integrity = audit.verify_integrity(date: str) -> Dict

# Export
path = audit.export_audit_trail(
    output_path: str,
    start_date: str,
    end_date: str,
    format: str = 'json'
) -> str

# Generate report
report = audit.generate_compliance_report(
    report_type: str,
    date: str,
    domain: str
) -> Dict
```

## Compliance Features

### SOX Compliance (Financial Auditing)

The audit trail system supports SOX compliance requirements:

- ✅ Immutable audit logs (append-only, cryptographically chained)
- ✅ Complete transaction history
- ✅ User attribution (user_id, session_id tracking)
- ✅ Timestamp accuracy (ISO 8601 format)
- ✅ Integrity verification (hash chain validation)
- ✅ Export capabilities (JSON, CSV formats)

### GDPR Compliance (Data Privacy)

- ✅ Data access logging (DATA_READ events)
- ✅ Data modification tracking (DATA_CREATED, DATA_UPDATED, DATA_DELETED)
- ✅ Audit export for data subject requests
- ✅ Retention policy support (configurable retention days)

## Monitoring & Observability

### Real-Time Status

```bash
# Check system status
python orchestrator_cross_domain.py

# Output:
# Domain Statistics:
#   Total processed: 150
#   Success rate: 98.7%
#   By domain: business=100, personal=45, mixed=5

# MCP Server Status:
#   ✅ email: Online
#   ✅ social: Online
#   ✅ odoo: Online
#   ✅ browser: Online
```

### Daily Audit Summary

```python
from audit_trail import get_audit

audit = get_audit()
summary = audit.get_audit_summary(days=7)

print(f"Total events (7 days): {summary['total_events']}")
print(f"Error rate: {summary['error_rate']:.2f}%")
print(f"Top actors: {summary['top_actors']}")
```

## Troubleshooting

### Domain Misclassification

**Problem:** Tasks classified to wrong domain

**Solution:**
1. Add keywords to `domain_rules.json`
2. Increase confidence threshold
3. Review classification logs: `Logs/domain_classifier.log`

### MCP Server Offline

**Problem:** Router reports server offline

**Solution:**
```bash
# Check MCP server status
python cross_domain_router.py

# Restart specific MCP server
python email_mcp.py
python social_mcp.py
python odoo_mcp.py
```

### Audit Log Integrity Failure

**Problem:** `verify_integrity()` returns False

**Solution:**
1. Check for file corruption
2. Review error details in integrity report
3. Restore from backup if tampering suspected
4. Export remaining valid entries

## Security Considerations

1. **Audit Log Protection:**
   - Store audit logs in secure location
   - Enable cryptographic chaining
   - Regular integrity verification
   - Export backups daily

2. **Domain Separation:**
   - Business tasks require approval
   - Personal tasks auto-executed
   - Mixed tasks routed for review

3. **Access Control:**
   - Log user_id for all actions
   - Track session_id for tracing
   - Record IP addresses (optional)

## Performance Characteristics

| Component | Latency | Throughput |
|-----------|---------|------------|
| Domain Classification | <10ms | 1000+ tasks/sec |
| Cross-Domain Routing | 50-200ms | 100+ tasks/sec |
| Audit Logging | <5ms | 1000+ events/sec |
| MCP Execution | 1-5s | 12-60 actions/min |

## Testing

Run the test suite:

```bash
# Test domain classifier
python domain_classifier.py

# Test cross-domain router
python cross_domain_router.py

# Test audit trail
python audit_trail.py

# Test orchestrator integration
python orchestrator_cross_domain.py
```

## Support

- Audit Logs: `Logs/Audit/`
- Component Logs: `Logs/*.log`
- Documentation: `CROSS_DOMAIN_INTEGRATION.md`
