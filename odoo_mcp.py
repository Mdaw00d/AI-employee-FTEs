#!/usr/bin/env python3
"""
Odoo MCP Server - JSON-RPC API for Odoo Accounting Operations
==============================================================
Provides a local MCP (Model Context Protocol) server for interacting with Odoo 19
via JSON-RPC APIs. Used by AI agents for accounting operations.

Features:
- Create invoices
- Read transactions
- Search partners/customers
- Payment registration
- Account reconciliation

Usage:
    python odoo_mcp.py

Server runs at: http://localhost:8070
Logs written to: Logs/odoo_mcp.log

Integration with Orchestrator:
    When accounting file detected in Needs_Action/, orchestrator calls:
    POST http://localhost:8070/rpc
    with method: create_invoice, get_transactions, etc.
"""

import os
import sys
import io
import json
import logging
import xmlrpc.client
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Optional, Dict, Any, List

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Scoop PostgreSQL path (user installation)
SCOOP_PG_PATH = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin")
if SCOOP_PG_PATH.exists():
    os.environ["PATH"] = str(SCOOP_PG_PATH) + os.pathsep + os.environ.get("PATH", "")

# Configuration - Match odoo_setup.py settings
ODOO_HOST = "localhost"
ODOO_PORT = 8069  # Odoo web interface port
ODOO_DB = "odoo_db"
ODOO_USER = "admin"
ODOO_PASSWORD = "admin"  # Using admin for now due to Odoo 19 permission changes

# MCP Server Configuration
MCP_HOST = "localhost"
MCP_PORT = 8070  # MCP server port (different from Odoo)

# Logging
LOG_DIR = Path("Logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "odoo_mcp.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OdooConnection:
    """Manages connection to Odoo via XML-RPC."""
    
    def __init__(self, host: str, port: int, db: str, user: str, password: str):
        self.host = host
        self.port = port
        self.db = db
        self.user = user
        self.password = password
        self.uid: Optional[int] = None
        self._common_proxy = None
        self._object_proxy = None
    
    @property
    def url_common(self) -> str:
        return f"http://{self.host}:{self.port}/xmlrpc/2/common"
    
    @property
    def url_object(self) -> str:
        return f"http://{self.host}:{self.port}/xmlrpc/2/object"
    
    @property
    def common(self) -> xmlrpc.client.ServerProxy:
        if self._common_proxy is None:
            self._common_proxy = xmlrpc.client.ServerProxy(self.url_common)
        return self._common_proxy
    
    @property
    def objects(self) -> xmlrpc.client.ServerProxy:
        if self._object_proxy is None:
            self._object_proxy = xmlrpc.client.ServerProxy(self.url_object)
        return self._object_proxy
    
    def authenticate(self) -> bool:
        """Authenticate with Odoo and get user ID."""
        try:
            logger.info(f"Authenticating with Odoo at {self.host}:{self.port}")
            self.uid = self.common.authenticate(self.db, self.user, self.password, {})
            
            if self.uid:
                logger.info(f"Authentication successful. User ID: {self.uid}")
                return True
            else:
                logger.error("Authentication failed - invalid credentials")
                return False
                
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Execute a method on an Odoo model."""
        if not self.uid:
            if not self.authenticate():
                raise Exception("Not authenticated with Odoo")
        
        try:
            result = self.objects.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
            logger.debug(f"Executed {model}.{method} - Result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error executing {model}.{method}: {e}")
            raise


class MCPServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP JSON-RPC API."""
    
    odoo: Optional[OdooConnection] = None
    demo_mode: bool = False

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info(f"HTTP: {args[0]}")
    
    def send_json_response(self, data: Dict, status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())
    
    def send_error_response(self, message: str, code: int = -32000):
        """Send JSON-RPC error response."""
        self.send_json_response({
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": None
        }, status=400)
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Handle JSON-RPC POST requests."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                request = json.loads(body)
            except json.JSONDecodeError as e:
                self.send_error_response(f"Invalid JSON: {e}")
                return
            
            # Validate JSON-RPC structure
            if not isinstance(request, dict):
                self.send_error_response("Request must be a JSON object")
                return
            
            method = request.get('method')
            params = request.get('params', {})
            request_id = request.get('id')
            
            if not method:
                self.send_error_response("Missing 'method' in request")
                return
            
            logger.info(f"RPC Method: {method}")
            logger.debug(f"Params: {params}")
            
            # Route to appropriate handler
            result = self.handle_method(method, params)
            
            # Send response
            response = {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
            self.send_json_response(response)
            
        except Exception as e:
            logger.exception(f"Error handling request: {e}")
            self.send_error_response(str(e))
    
    def handle_method(self, method: str, params: Dict) -> Any:
        """Route JSON-RPC method to appropriate handler."""
        
        methods = {
            # Accounting Operations
            "create_invoice": self.create_invoice,
            "get_transactions": self.get_transactions,
            "get_invoice": self.get_invoice,
            "list_invoices": self.list_invoices,
            "register_payment": self.register_payment,
            "reconcile_payments": self.reconcile_payments,
            
            # Partner/Customer Operations
            "search_partner": self.search_partner,
            "create_partner": self.create_partner,
            "get_partner": self.get_partner,
            
            # Account Operations
            "get_accounts": self.get_accounts,
            "get_journal_items": self.get_journal_items,
            
            # System Operations
            "health_check": self.health_check,
            "get_version": self.get_version,
        }
        
        if method not in methods:
            raise Exception(f"Unknown method: {method}")
        
        return methods[method](params)
    
    # ==================== Accounting Methods ====================
    
    def create_invoice(self, params: Dict) -> Dict:
        """
        Create a customer invoice in Odoo.

        Params:
            partner_id: int - Customer/Partner ID
            amount: float - Invoice amount (excluding tax)
            invoice_date: str - Invoice date (YYYY-MM-DD), optional
            due_date: str - Due date (YYYY-MM-DD), optional
            description: str - Invoice line description
            account_id: int - Revenue account ID, optional
            tax_ids: list - Tax IDs to apply, optional
            reference: str - Customer reference, optional

        Returns:
            invoice_id: int - Created invoice ID
            name: str - Invoice number
            amount_total: float - Total amount including tax
        """
        # Debug logging
        logger.info(f"DEBUG: MCPServerHandler.demo_mode={MCPServerHandler.demo_mode}, MCPServerHandler.odoo={MCPServerHandler.odoo}")
        
        # Demo mode - return mock response
        if MCPServerHandler.demo_mode or not MCPServerHandler.odoo:
            logger.info("DEMO MODE: Returning mock invoice response")
            return {
                'invoice_id': 1001,
                'name': 'INV/2026/DEMO/001',
                'amount_total': float(params.get('amount', 1000)),
                'state': 'draft',
                'demo_mode': True,
                'message': 'Odoo not initialized. This is a mock response.'
            }
        
        logger.info(f"Creating invoice for partner {params.get('partner_id')}")

        partner_id = params.get('partner_id')
        if not partner_id:
            raise Exception("partner_id is required")

        amount = float(params.get('amount', 0))
        invoice_date = params.get('invoice_date', datetime.now().strftime('%Y-%m-%d'))
        due_date = params.get('due_date')
        description = params.get('description', 'Service/Product')
        reference = params.get('reference')

        # Prepare invoice lines
        invoice_line_vals = [[0, 0, {
            'name': description,
            'quantity': 1,
            'price_unit': amount,
        }]]

        # Add taxes if specified
        if params.get('tax_ids'):
            invoice_line_vals[0][2]['tax_ids'] = [[6, 0, params['tax_ids']]]

        # Create invoice
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner_id,
            'invoice_date': invoice_date,
            'invoice_line_ids': invoice_line_vals,
        }

        if due_date:
            invoice_vals['invoice_date_due'] = due_date

        if reference:
            invoice_vals['ref'] = reference

        invoice_id = self.odoo.execute('account.move', 'create', invoice_vals)

        # Get invoice details
        invoice_data = self.odoo.execute(
            'account.move', 'read', [invoice_id],
            ['name', 'amount_total', 'amount_untaxed', 'amount_tax', 'state']
        )
        
        result = {
            'invoice_id': invoice_id,
            'name': invoice_data[0]['name'] if invoice_data else None,
            'amount_total': invoice_data[0]['amount_total'] if invoice_data else amount,
            'state': invoice_data[0]['state'] if invoice_data else 'draft',
        }
        
        logger.info(f"Invoice created: {result}")
        return result
    
    def get_transactions(self, params: Dict) -> List[Dict]:
        """
        Get accounting transactions within date range.

        Params:
            date_from: str - Start date (YYYY-MM-DD)
            date_to: str - End date (YYYY-MM-DD)
            move_type: str - Filter by type (out_invoice, in_invoice, payment, etc.)
            state: str - Filter by state (posted, draft, cancel)
            partner_id: int - Filter by partner
            limit: int - Max results (default 100)

        Returns:
            List of transaction records
        """
        # Demo mode - return mock response
        if self.demo_mode or not self.odoo:
            logger.info("DEMO MODE: Returning mock transactions")
            return [
                {
                    'id': 1,
                    'name': 'INV/2026/DEMO/001',
                    'date': '2026-03-01',
                    'move_type': 'out_invoice',
                    'state': 'posted',
                    'partner_id': {'id': 1, 'name': 'Demo Customer'},
                    'amount_total': 5000.00,
                    'payment_state': 'not_paid',
                    'demo_mode': True
                },
                {
                    'id': 2,
                    'name': 'INV/2026/DEMO/002',
                    'date': '2026-03-02',
                    'move_type': 'out_invoice',
                    'state': 'draft',
                    'partner_id': {'id': 2, 'name': 'Test Corp'},
                    'amount_total': 2500.00,
                    'payment_state': 'not_paid',
                    'demo_mode': True
                }
            ]
        
        logger.info(f"Getting transactions from {params.get('date_from')} to {params.get('date_to')}")

        date_from = params.get('date_from', (datetime.now().replace(day=1)).strftime('%Y-%m-%d'))
        date_to = params.get('date_to', datetime.now().strftime('%Y-%m-%d'))
        limit = params.get('limit', 100)

        # Build domain filter
        domain = [
            ['date', '>=', date_from],
            ['date', '<=', date_to],
        ]

        if params.get('move_type'):
            domain.append(['move_type', '=', params['move_type']])

        if params.get('state'):
            domain.append(['state', '=', params['state']])

        if params.get('partner_id'):
            domain.append(['partner_id', '=', params['partner_id']])

        # Search and read
        transactions = self.odoo.execute(
            'account.move', 'search_read',
            domain,
            fields=[
                'name', 'date', 'move_type', 'state', 'partner_id',
                'amount_total', 'amount_untaxed', 'amount_tax',
                'payment_state', 'ref', 'invoice_origin'
            ],
            limit=limit,
            order='date DESC'
        )

        # Format partner_id (it's a tuple [id, name])
        for tx in transactions:
            if isinstance(tx.get('partner_id'), (list, tuple)):
                tx['partner_id'] = {'id': tx['partner_id'][0], 'name': tx['partner_id'][1]}

        logger.info(f"Found {len(transactions)} transactions")
        return transactions
    
    def get_invoice(self, params: Dict) -> Dict:
        """
        Get invoice details by ID or name.
        
        Params:
            invoice_id: int - Invoice database ID, or
            name: str - Invoice number (e.g., "INV/2026/00001")
        
        Returns:
            Full invoice record with lines
        """
        invoice_id = params.get('invoice_id')
        invoice_name = params.get('name')
        
        if not invoice_id and not invoice_name:
            raise Exception("invoice_id or name is required")
        
        # Search for invoice
        domain = []
        if invoice_id:
            domain.append(['id', '=', invoice_id])
        if invoice_name:
            domain.append(['name', '=', invoice_name])
        
        invoices = self.odoo.execute(
            'account.move', 'search_read',
            domain,
            fields=['__all__']
        )
        
        if not invoices:
            raise Exception("Invoice not found")
        
        invoice = invoices[0]
        
        # Get invoice lines
        lines = self.odoo.execute(
            'account.move.line', 'search_read',
            [['move_id', '=', invoice['id']]],
            fields=['name', 'quantity', 'price_unit', 'price_subtotal', 'price_total']
        )
        
        invoice['lines'] = lines
        return invoice
    
    def list_invoices(self, params: Dict) -> List[Dict]:
        """
        List invoices with optional filtering.
        
        Params:
            partner_id: int - Filter by customer
            state: str - Filter by state (draft, posted, cancel)
            payment_state: str - Filter by payment (not_paid, partial, paid)
            limit: int - Max results
        """
        domain = [['move_type', 'in', ['out_invoice', 'out_refund']]]
        
        if params.get('partner_id'):
            domain.append(['partner_id', '=', params['partner_id']])
        
        if params.get('state'):
            domain.append(['state', '=', params['state']])
        
        if params.get('payment_state'):
            domain.append(['payment_state', '=', params['payment_state']])
        
        invoices = self.odoo.execute(
            'account.move', 'search_read',
            domain,
            fields=['name', 'date', 'partner_id', 'amount_total', 'payment_state', 'state'],
            limit=params.get('limit', 50),
            order='date DESC'
        )
        
        # Format partner_id
        for inv in invoices:
            if isinstance(inv.get('partner_id'), (list, tuple)):
                inv['partner_id'] = {'id': inv['partner_id'][0], 'name': inv['partner_id'][1]}
        
        return invoices
    
    def register_payment(self, params: Dict) -> Dict:
        """
        Register a payment for an invoice.
        
        Params:
            invoice_id: int - Invoice to pay
            amount: float - Payment amount
            payment_date: str - Payment date (YYYY-MM-DD)
            payment_method: str - Payment method name
            reference: str - Payment reference/note
        
        Returns:
            payment_id: int - Created payment ID
            reconciled: bool - Whether fully reconciled
        """
        invoice_id = params.get('invoice_id')
        if not invoice_id:
            raise Exception("invoice_id is required")
        
        amount = float(params.get('amount', 0))
        payment_date = params.get('payment_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Get invoice to find journal
        invoice = self.odoo.execute(
            'account.move', 'read', [invoice_id],
            ['journal_id', 'currency_id', 'amount_residual']
        )[0]
        
        # Create payment using account.payment.register wizard
        payment_register_vals = {
            'payment_date': payment_date,
            'amount': amount,
            'journal_id': invoice['journal_id'][0] if isinstance(invoice['journal_id'], (list, tuple)) else invoice['journal_id'],
        }
        
        if params.get('reference'):
            payment_register_vals['memo'] = params['reference']
        
        # Create payment register
        payment_register_id = self.odoo.execute(
            'account.payment.register', 'create', payment_register_vals
        )
        
        # Execute payment (this reconciles with invoice)
        self.odoo.execute(
            'account.payment.register', 'action_create_payments',
            [payment_register_id],
            {'active_ids': [invoice_id]}
        )
        
        # Check payment state
        invoice_updated = self.odoo.execute(
            'account.move', 'read', [invoice_id],
            ['payment_state']
        )[0]
        
        result = {
            'invoice_id': invoice_id,
            'amount': amount,
            'payment_state': invoice_updated.get('payment_state'),
            'reconciled': invoice_updated.get('payment_state') == 'paid',
        }
        
        logger.info(f"Payment registered: {result}")
        return result
    
    def reconcile_payments(self, params: Dict) -> Dict:
        """
        Reconcile payments with invoices automatically.
        
        Params:
            partner_id: int - Partner to reconcile
            limit: int - Max invoices to process
        
        Returns:
            reconciled_count: int - Number of reconciliations made
            total_amount: float - Total amount reconciled
        """
        logger.info(f"Reconciling payments for partner {params.get('partner_id')}")
        
        # This is a simplified reconciliation
        # In production, use Odoo's automatic reconciliation
        
        result = {
            'reconciled_count': 0,
            'total_amount': 0,
            'message': 'Manual reconciliation recommended for complex cases'
        }
        
        return result
    
    # ==================== Partner Methods ====================
    
    def search_partner(self, params: Dict) -> List[Dict]:
        """
        Search for partners/customers.
        
        Params:
            name: str - Search term in partner name
            email: str - Search by email
            phone: str - Search by phone
            vat: str - Search by VAT number
            limit: int - Max results
        
        Returns:
            List of matching partners
        """
        domain = []
        
        if params.get('name'):
            domain.append(['name', 'ilike', params['name']])
        
        if params.get('email'):
            domain.append(['email', 'ilike', params['email']])
        
        if params.get('phone'):
            domain.append(['phone', 'ilike', params['phone']])
        
        if params.get('vat'):
            domain.append(['vat', 'ilike', params['vat']])
        
        partners = self.odoo.execute(
            'res.partner', 'search_read',
            domain,
            fields=['name', 'email', 'phone', 'vat', 'street', 'city', 'country_id'],
            limit=params.get('limit', 50)
        )
        
        # Format country_id
        for p in partners:
            if isinstance(p.get('country_id'), (list, tuple)):
                p['country_id'] = {'id': p['country_id'][0], 'name': p['country_id'][1]}
        
        return partners
    
    def create_partner(self, params: Dict) -> Dict:
        """
        Create a new partner/customer.
        
        Params:
            name: str - Partner name (required)
            email: str - Email address
            phone: str - Phone number
            street: str - Street address
            city: str - City
            country_id: int - Country ID
            vat: str - VAT number
            customer: bool - Is customer (default True)
        
        Returns:
            partner_id: int - Created partner ID
            name: str - Partner name
        """
        name = params.get('name')
        if not name:
            raise Exception("name is required")
        
        partner_vals = {
            'name': name,
            'customer': params.get('customer', True),
        }
        
        for field in ['email', 'phone', 'street', 'city', 'vat']:
            if params.get(field):
                partner_vals[field] = params[field]
        
        if params.get('country_id'):
            partner_vals['country_id'] = params['country_id']
        
        partner_id = self.odoo.execute('res.partner', 'create', partner_vals)
        
        result = {
            'partner_id': partner_id,
            'name': name,
        }
        
        logger.info(f"Partner created: {result}")
        return result
    
    def get_partner(self, params: Dict) -> Dict:
        """
        Get partner details by ID.
        
        Params:
            partner_id: int - Partner database ID
        
        Returns:
            Full partner record
        """
        partner_id = params.get('partner_id')
        if not partner_id:
            raise Exception("partner_id is required")
        
        partners = self.odoo.execute(
            'res.partner', 'read', [partner_id]
        )
        
        if not partners:
            raise Exception("Partner not found")
        
        return partners[0]
    
    # ==================== Account Methods ====================
    
    def get_accounts(self, params: Dict) -> List[Dict]:
        """
        Get chart of accounts.
        
        Params:
            account_type: str - Filter by type (asset, liability, equity, income, expense)
            code_prefix: str - Filter by code prefix
        
        Returns:
            List of accounts
        """
        domain = [['company_id', '=', self.odoo.execute('res.company', 'search_read', [], ['id'])[0]['id']]]
        
        if params.get('account_type'):
            type_mapping = {
                'asset': 'asset',
                'liability': 'liability',
                'equity': 'equity',
                'income': 'income',
                'expense': 'expense',
            }
            domain.append(['account_type', '=', type_mapping.get(params['account_type'], params['account_type'])])
        
        if params.get('code_prefix'):
            domain.append(['code', '=like', f"{params['code_prefix']}%"])
        
        accounts = self.odoo.execute(
            'account.account', 'search_read',
            domain,
            fields=['code', 'name', 'account_type', 'user_type_id'],
            limit=500
        )
        
        return accounts
    
    def get_journal_items(self, params: Dict) -> List[Dict]:
        """
        Get journal items (account move lines).
        
        Params:
            date_from: str - Start date
            date_to: str - End date
            account_id: int - Filter by account
            partner_id: int - Filter by partner
        
        Returns:
            List of journal items
        """
        domain = []
        
        if params.get('date_from') or params.get('date_to'):
            date_from = params.get('date_from', '1900-01-01')
            date_to = params.get('date_to', datetime.now().strftime('%Y-%m-%d'))
            domain.append(['date', '>=', date_from])
            domain.append(['date', '<=', date_to])
        
        if params.get('account_id'):
            domain.append(['account_id', '=', params['account_id']])
        
        if params.get('partner_id'):
            domain.append(['partner_id', '=', params['partner_id']])
        
        items = self.odoo.execute(
            'account.move.line', 'search_read',
            domain,
            fields=['date', 'name', 'account_id', 'partner_id', 'debit', 'credit', 'balance'],
            limit=params.get('limit', 100)
        )
        
        return items
    
    # ==================== System Methods ====================
    
    def health_check(self, params: Dict) -> Dict:
        """Check server and Odoo connection health."""
        odoo_connected = False
        odoo_version = None

        try:
            if self.odoo and self.odoo.uid:
                odoo_connected = True
                # Get Odoo version using Odoo 19 API
                version_info = self.odoo.execute(
                    'ir.module.module', 'search_read',
                    [['name', '=', 'base']],
                    fields=['latest_version'],
                    limit=1
                )
                if version_info:
                    odoo_version = version_info[0].get('latest_version', 'unknown')
        except Exception as e:
            logger.error(f"Health check failed: {e}")

        return {
            'status': 'healthy' if odoo_connected else 'degraded',
            'odoo_connected': odoo_connected,
            'odoo_version': odoo_version,
            'timestamp': datetime.now().isoformat(),
        }
    
    def get_version(self, params: Dict) -> Dict:
        """Get MCP server and Odoo version info."""
        return {
            'mcp_server': 'Odoo MCP Server v1.0',
            'odoo_host': f"{ODOO_HOST}:{ODOO_PORT}",
            'odoo_database': ODOO_DB,
            'timestamp': datetime.now().isoformat(),
        }


def main():
    """Start the MCP server."""
    print_header()

    # Initialize Odoo connection
    print("Initializing Odoo connection...")
    odoo = OdooConnection(ODOO_HOST, ODOO_PORT, ODOO_DB, ODOO_USER, ODOO_PASSWORD)

    odoo_connected = odoo.authenticate()
    
    logger.info(f"odoo_connected={odoo_connected}, odoo.uid={odoo.uid}")
    logger.info(f"Setting MCPServerHandler.odoo={odoo if odoo_connected else None}, demo_mode={not odoo_connected}")
    
    if not odoo_connected:
        print("\n⚠️  Odoo not fully initialized yet.")
        print("\n📋 To initialize Odoo database, run:")
        print("   python init_odoo_db.py")
        print("\n🔧 MCP Server will start in DEMO MODE.")
        print("   API calls will return mock responses until Odoo is ready.\n")
    else:
        print("✅ Connected to Odoo")

    # Set Odoo connection on handler (even if None for demo mode)
    MCPServerHandler.odoo = odoo if odoo_connected else None
    MCPServerHandler.demo_mode = not odoo_connected
    
    logger.info(f"Verified: MCPServerHandler.odoo={MCPServerHandler.odoo}, demo_mode={MCPServerHandler.demo_mode}")
    
    # Start HTTP server
    server_address = (MCP_HOST, MCP_PORT)
    httpd = HTTPServer(server_address, MCPServerHandler)
    
    print(f"\n🚀 Odoo MCP Server started")
    print(f"   Endpoint: http://{MCP_HOST}:{MCP_PORT}/rpc")
    print(f"   Logs: {LOG_FILE}")
    print(f"\n📡 Available Methods:")
    print("   - create_invoice")
    print("   - get_transactions")
    print("   - list_invoices")
    print("   - register_payment")
    print("   - search_partner")
    print("   - create_partner")
    print("   - get_accounts")
    print("   - health_check")
    print(f"\n💡 Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped by user")
        httpd.shutdown()


def print_header():
    print("""
╔══════════════════════════════════════════════════════════╗
║           Odoo MCP Server - JSON-RPC API                 ║
║           For AI Agent Accounting Operations             ║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
