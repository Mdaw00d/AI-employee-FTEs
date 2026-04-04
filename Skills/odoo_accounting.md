# Skill: Odoo Accounting Integration

## Name
`odoo_accounting`

## Trigger
- **File Pattern**: `Needs_Action/accounting_*.md`, `Needs_Action/invoice_*.md`
- **API Calls**: JSON-RPC requests from orchestrator
- **Schedule**: Daily reconciliation at 5:00 AM

## Inputs
| Input | Description |
|-------|-------------|
| Request file | Specific accounting action requested (create invoice, read transactions, etc.) |
| `Briefings/odoo_config.md` | Odoo instance URL, database name, API credentials |
| `Approved/vendor_list.md` | Verified vendor/customer IDs for validation |
| `Company_Handbook.md` | Accounting policies, approval thresholds |

## Steps
1. **Parse Request**
   - Identify action type: `create_invoice`, `read_transactions`, `reconcile`, `report`, `payment_register`
   - Extract required parameters (amounts, dates, partner IDs, etc.)
   - Validate request against accounting policies

2. **Authenticate with Odoo**
   - Read credentials from `Briefings/odoo_config.md`
   - Establish JSON-RPC session
   - Handle authentication errors gracefully

3. **Execute Action**

   ### Create Invoice
   - Validate partner/customer exists
   - Create invoice record with line items
   - Apply correct tax rules
   - Return invoice number and status

   ### Read Transactions
   - Query account.move for specified period
   - Filter by type (invoice, bill, payment, journal entry)
   - Return formatted transaction list

   ### Reconcile Payments
   - Match incoming payments to open invoices
   - Flag partial payments or discrepancies
   - Create reconciliation records

   ### Generate Report
   - Aged Receivables/Payables
   - Profit & Loss summary
   - Cash flow statement
   - General Ledger extract

4. **Validate Results**
   - Check for errors in Odoo response
   - Verify amounts and account balances
   - Ensure audit trail is complete

5. **Log Transaction**
   - Record all API calls in `Briefings/odoo_audit_log.md`
   - Store request/response for compliance
   - Update local cache if applicable

## Outputs
| Output | Location | Description |
|--------|----------|-------------|
| Result File | `Done/accounting_<action>_<id>.md` | Completed action with results |
| Approval Request | `Pending_Approval/accounting_<action>_<id>.md` | Actions requiring human approval |
| Audit Log | `Briefings/odoo_audit_log.md` | Complete log of all Odoo interactions |
| Error Log | `Needs_Action/accounting_errors.md` | Failed operations requiring attention |

## JSON-RPC Methods Reference

```json
// Authenticate
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "service": "common",
    "method": "authenticate",
    "args": ["db_name", "username", "api_key"]
  },
  "id": 1
}

// Create Invoice
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": [
      "db_name",
      "user_id",
      "api_key",
      "account.move",
      "create",
      [[{
        "move_type": "out_invoice",
        "partner_id": 123,
        "invoice_line_ids": [[0, 0, {
          "product_id": 456,
          "quantity": 1,
          "price_unit": 1000.00
        }]]
      }]]
    ]
  },
  "id": 2
}

// Search Transactions
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": [
      "db_name",
      "user_id",
      "api_key",
      "account.move",
      "search_read",
      [[["date", ">=", "2026-03-01"]]],
      {"fields": ["name", "date", "amount_total", "state"]}
    ]
  },
  "id": 3
}
```

## Example Output: Done/accounting_invoice_001.md
```markdown
# Accounting Action Complete

**Action**: Create Invoice
**Request**: Needs_Action/invoice_new_client.md
**Timestamp**: 2026-03-04 10:23:45

---

## Result

**Status**: ✅ Success

**Invoice Details**:
- **Invoice Number**: INV/2026/00342
- **Customer**: Acme Corporation (ID: 1234)
- **Amount**: $5,250.00 (incl. tax)
- **Due Date**: 2026-04-03
- **Status**: Draft

**Line Items**:
| Description | Quantity | Unit Price | Total |
|-------------|----------|------------|-------|
| Consulting Services - March | 35 hrs | $150.00 | $5,250.00 |

---

## Odoo Response
```json
{
  "jsonrpc": "2.0",
  "result": 89234,
  "id": 2
}
```

**Internal Record ID**: 89234

---

**Audit Reference**: Briefings/odoo_audit_log.md#2026-03-04-001
```

## Example Output: Pending_Approval/accounting_payment_approval_001.md
```markdown
# Accounting Approval Required

**Action**: Payment Registration (Above Threshold)
**Request**: Needs_Action/payment_large_vendor.md

---

## Payment Details

- **Vendor**: Enterprise Solutions Ltd
- **Amount**: $25,000.00
- **Invoice Reference**: BILL/2026/00189
- **Due Date**: 2026-03-10
- **Payment Method**: Bank Transfer

---

## Approval Required

This payment exceeds the automated approval threshold of $10,000.

**Policy Reference**: Company_Handbook.md §4.2 - Payment Authorization

---

**Status**: ⏳ Pending Human Approval
**Requested**: 2026-03-04 11:00:00
**Approver**: Finance Manager

[ ] Approved
[ ] Rejected - Reason: _______________
```
