# Odoo 19 + MCP Server Setup Complete

## Status: ✅ MCP Server Running (Demo Mode)

### What's Working

| Component | Status | Notes |
|-----------|--------|-------|
| PostgreSQL 18.3 | ✅ Running | Scoop installation |
| Database `odoo_db` | ✅ Created | User: odoo_user |
| Odoo 19 Source | ✅ Downloaded | C:\Odoo19\odoo-master |
| Python Dependencies | ✅ Installed | All requirements |
| MCP Server | ✅ Running | http://localhost:8070/rpc (Demo Mode) |
| Odoo Web Server | ⚠️ Needs Init | Database schema pending |

### MCP Server API (Demo Mode)

The MCP server is running and responding with **mock data** until Odoo database is initialized.

**Test Endpoints:**

```powershell
# Health Check
$body = '{"jsonrpc":"2.0","method":"health_check","id":1}'
Invoke-RestMethod -Uri 'http://localhost:8070/rpc' -Method Post -Body $body -ContentType 'application/json'

# Create Invoice (Mock)
$body = '{"jsonrpc":"2.0","method":"create_invoice","params":{"partner_id":1,"amount":5000,"description":"Consulting Services"},"id":1}'
Invoke-RestMethod -Uri 'http://localhost:8070/rpc' -Method Post -Body $body -ContentType 'application/json'

# Get Transactions (Mock)
$body = '{"jsonrpc":"2.0","method":"get_transactions","params":{"date_from":"2026-03-01","date_to":"2026-03-31"},"id":1}'
Invoke-RestMethod -Uri 'http://localhost:8070/rpc' -Method Post -Body $body -ContentType 'application/json'
```

## Next Step: Initialize Odoo Database

To get full Odoo functionality (not demo mode), run:

```cmd
python init_odoo_db.py
```

This will:
1. Stop any running Odoo instances
2. Initialize the database schema (2-5 minutes)
3. Install all Odoo modules

After initialization:
1. Restart MCP: `python odoo_mcp.py`
2. MCP will auto-detect Odoo and switch to live mode

## File Summary

| File | Purpose |
|------|---------|
| `odoo_setup.py` | Initial Odoo setup script |
| `odoo_mcp.py` | MCP JSON-RPC API server |
| `start_all.py` | Complete startup script |
| `init_odoo_db.py` | Database initialization |
| `complete_setup.bat` | Windows batch startup |
| `ODOO_INTEGRATION.md` | Integration documentation |
| `Skills/odoo_accounting.md` | Agent skill definition |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Orchestrator  │────▶│  odoo_mcp.py    │────▶│   Odoo 19       │
│   (AI Agent)    │     │  (MCP Server)   │     │   (localhost)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
  Needs_Action/           JSON-RPC API           PostgreSQL
  Pending_Approval/       localhost:8070         localhost:5432
```

## Integration Example

When orchestrator detects `Needs_Action/accounting_*.md`:

```python
import requests

# Call MCP server
response = requests.post('http://localhost:8070/rpc', json={
    'jsonrpc': '2.0',
    'method': 'create_invoice',
    'params': {
        'partner_id': 123,
        'amount': 5000.00,
        'description': 'Consulting Services'
    },
    'id': 1
})

result = response.json()['result']
print(f"Invoice created: {result['name']} - ${result['amount_total']}")
```

## Troubleshooting

### MCP Server Not Starting
```cmd
# Check if port 8070 is in use
netstat -ano | findstr :8070

# Kill process if needed
taskkill /F /PID <pid>
```

### Odoo Database Issues
```cmd
# Check PostgreSQL
psql -U postgres -l

# Connect to odoo_db
psql -U odoo_user -d odoo_db
```

### Restart Everything
```cmd
# Stop all Python processes
taskkill /F /IM python.exe

# Start fresh
python odoo_mcp.py
```

## Ports Used

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | ✅ Running |
| Odoo Web | 8069 | ⚠️ Needs init |
| MCP Server | 8070 | ✅ Running |

## Demo Mode Responses

### create_invoice
```json
{
  "invoice_id": 1001,
  "name": "INV/2026/DEMO/001",
  "amount_total": 5000.0,
  "state": "draft",
  "demo_mode": true,
  "message": "Odoo not initialized. This is a mock response."
}
```

### get_transactions
```json
[
  {
    "id": 1,
    "name": "INV/2026/DEMO/001",
    "date": "2026-03-01",
    "move_type": "out_invoice",
    "state": "posted",
    "partner_id": {"id": 1, "name": "Demo Customer"},
    "amount_total": 5000.00,
    "payment_state": "not_paid",
    "demo_mode": true
  }
]
```

---

**Generated:** 2026-03-04  
**Hackathon:** Bronze Tier → Gold Tier  
**Status:** Ready for integration testing
