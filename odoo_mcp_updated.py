#!/usr/bin/env python3
"""
Odoo MCP Server - JSON-RPC API for Odoo Accounting Operations
==============================================================
Updated with retry_handler for error recovery and graceful degradation.

Features:
- Create invoices, read transactions, search partners
- Exponential backoff retry on transient errors
- Demo mode fallback when Odoo unavailable
- Comprehensive JSON logging to Logs/YYYY-MM-DD.json

Usage:
    python odoo_mcp.py

Server runs at: http://localhost:8070
Logs written to: Logs/odoo_mcp.log
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

# Import retry handler
from retry_handler import (
    retry_with_backoff,
    log_action,
    quarantine_item,
    classify_error,
    get_system_health
)

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Scoop PostgreSQL path
SCOOP_PG_PATH = Path(r"C:\Users\LAPTER.PK\scoop\apps\postgresql\current\bin")
if SCOOP_PG_PATH.exists():
    os.environ["PATH"] = str(SCOOP_PG_PATH) + os.pathsep + os.environ.get("PATH", "")

# ============================================================================
# Configuration
# ============================================================================

# Odoo Connection Settings
ODOO_HOST = "localhost"
ODOO_PORT = 8069
ODOO_DB = "odoo_db"
ODOO_USER = "admin"
ODOO_PASSWORD = "admin"

# MCP Server Configuration
MCP_HOST = "localhost"
MCP_PORT = 8070

# Retry Configuration
MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0

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


# ============================================================================
# Odoo Connection with Retry
# ============================================================================

class OdooConnection:
    """Manages connection to Odoo via XML-RPC with retry support."""

    def __init__(self, host: str, port: int, db: str, user: str, password: str):
        self.host = host
        self.port = port
        self.db = db
        self.user = user
        self.password = password
        self.uid: Optional[int] = None
        self._common_proxy = None
        self._object_proxy = None
        self._connection_failed = False
        self._last_success: Optional[datetime] = None

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

    @retry_with_backoff(
        max_attempts=MAX_RETRIES,
        base_delay=BASE_DELAY,
        max_delay=MAX_DELAY,
        log_actor="odoo_mcp",
        quarantine_on_failure=False
    )
    def authenticate(self) -> bool:
        """Authenticate with Odoo and get user ID."""
        try:
            logger.info(f"Authenticating with Odoo at {self.host}:{self.port}")
            
            self.uid = self.common.authenticate(self.db, self.user, self.password, {})

            if self.uid:
                logger.info(f"Authentication successful. User ID: {self.uid}")
                self._connection_failed = False
                self._last_success = datetime.now()
                
                log_action(
                    action_type="authenticate",
                    actor="odoo_mcp",
                    target=f"{self.host}:{self.port}",
                    parameters={"db": self.db, "user": self.user},
                    result="success"
                )
                return True
            else:
                logger.error("Authentication failed - invalid credentials")
                log_action(
                    action_type="authenticate",
                    actor="odoo_mcp",
                    target=f"{self.host}:{self.port}",
                    parameters={"db": self.db, "user": self.user},
                    result="failure",
                    error="Invalid credentials"
                )
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self._connection_failed = True
            
            log_action(
                action_type="authenticate",
                actor="odoo_mcp",
                target=f"{self.host}:{self.port}",
                parameters={"db": self.db, "user": self.user},
                result="failure",
                error=str(e)
            )
            raise

    @retry_with_backoff(
        max_attempts=MAX_RETRIES,
        base_delay=BASE_DELAY,
        max_delay=MAX_DELAY,
        log_actor="odoo_mcp",
        quarantine_on_failure=False
    )
    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Execute a method on an Odoo model with retry."""
        if not self.uid:
            if not self.authenticate():
                raise Exception("Not authenticated with Odoo")

        try:
            result = self.objects.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
            
            self._last_success = datetime.now()
            
            logger.debug(f"Executed {model}.{method} - Result: {result}")
            
            log_action(
                action_type="execute",
                actor="odoo_mcp",
                target=f"{model}.{method}",
                parameters={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
                result="success"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing {model}.{method}: {e}")
            
            log_action(
                action_type="execute",
                actor="odoo_mcp",
                target=f"{model}.{method}",
                parameters={"model": model, "method": method},
                result="failure",
                error=str(e)
            )
            raise

    def is_connected(self) -> bool:
        """Check if connection is healthy."""
        if self._connection_failed:
            return False
        if self.uid is None:
            return False
        return True


# ============================================================================
# MCP Server Handler
# ============================================================================

class MCPServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP JSON-RPC API with retry support."""

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

    @retry_with_backoff(
        max_attempts=2,
        base_delay=0.5,
        log_actor="odoo_mcp_server",
        quarantine_on_failure=False
    )
    def do_POST(self):
        """Handle JSON-RPC POST requests with retry."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')

            try:
                request = json.loads(body)
            except json.JSONDecodeError as e:
                self.send_error_response(f"Invalid JSON: {e}")
                return

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

            result = self.handle_method(method, params)

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

    # ==================== Accounting Methods with Retry ====================

    @retry_with_backoff(
        max_attempts=MAX_RETRIES,
        base_delay=BASE_DELAY,
        max_delay=MAX_DELAY,
        log_actor="odoo_mcp",
        quarantine_on_failure=False
    )
    def create_invoice(self, params: Dict) -> Dict:
        """
        Create a customer invoice in Odoo with retry.
        """
        logger.info(f"DEBUG: MCPServerHandler.demo_mode={MCPServerHandler.demo_mode}, MCPServerHandler.odoo={MCPServerHandler.odoo}")

        # Demo mode - return mock response
        if MCPServerHandler.demo_mode or not MCPServerHandler.odoo:
            logger.info("DEMO MODE: Returning mock invoice response")
            
            log_action(
                action_type="create_invoice",
                actor="odoo_mcp",
                target="demo_mode",
                parameters=params,
                result="success",
                error="Demo mode - mock response"
            )
            
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
        description = params.get('description', 'Invoice')

        # Create invoice in Odoo
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': partner_id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [(0, 0, {
                'name': description,
                'price_unit': amount,
                'quantity': 1,
            })]
        }

        if due_date:
            invoice_vals['invoice_date_due'] = due_date

        invoice_id = MCPServerHandler.odoo.execute(
            'account.move',
            'create',
            [invoice_vals]
        )

        logger.info(f"Invoice created: {invoice_id}")
        
        log_action(
            action_type="create_invoice",
            actor="odoo_mcp",
            target=str(invoice_id),
            parameters=params,
            result="success"
        )

        return {
            'invoice_id': invoice_id,
            'name': f'INV/{invoice_id}',
            'amount_total': amount,
            'state': 'draft'
        }

    @retry_with_backoff(
        max_attempts=MAX_RETRIES,
        base_delay=BASE_DELAY,
        max_delay=MAX_DELAY,
        log_actor="odoo_mcp",
        quarantine_on_failure=False
    )
    def get_transactions(self, params: Dict) -> Dict:
        """
        Get transactions from Odoo with retry.
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.odoo:
            logger.info("DEMO MODE: Returning mock transactions response")
            
            log_action(
                action_type="get_transactions",
                actor="odoo_mcp",
                target="demo_mode",
                parameters=params,
                result="success",
                error="Demo mode - mock response"
            )
            
            return {
                'invoices': [],
                'payments': [],
                'total_revenue': 0,
                'total_payments': 0,
                'outstanding_ar': 0,
                'demo_mode': True
            }

        date_from = params.get('date_from')
        date_to = params.get('date_to')

        # Query invoices
        domain = []
        if date_from:
            domain.append(['invoice_date', '>=', date_from])
        if date_to:
            domain.append(['invoice_date', '<=', date_to])

        invoices = MCPServerHandler.odoo.execute(
            'account.move',
            'search_read',
            [domain],
            ['name', 'amount_total', 'amount_residual', 'state']
        )

        # Calculate totals
        total_revenue = sum(inv.get('amount_total', 0) for inv in invoices if inv.get('move_type') == 'out_invoice')
        total_payments = sum(inv.get('amount_total', 0) - inv.get('amount_residual', 0) for inv in invoices)
        outstanding_ar = sum(inv.get('amount_residual', 0) for inv in invoices if inv.get('move_type') == 'out_invoice')

        logger.info(f"Retrieved {len(invoices)} transactions")
        
        log_action(
            action_type="get_transactions",
            actor="odoo_mcp",
            target="account.move",
            parameters=params,
            result="success"
        )

        return {
            'invoices': invoices,
            'payments': [],
            'total_revenue': total_revenue,
            'total_payments': total_payments,
            'outstanding_ar': outstanding_ar
        }

    @retry_with_backoff(
        max_attempts=MAX_RETRIES,
        base_delay=BASE_DELAY,
        max_delay=MAX_DELAY,
        log_actor="odoo_mcp",
        quarantine_on_failure=False
    )
    def search_partner(self, params: Dict) -> Dict:
        """
        Search for partners/customers with retry.
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.odoo:
            logger.info("DEMO MODE: Returning mock partner search response")
            
            log_action(
                action_type="search_partner",
                actor="odoo_mcp",
                target="demo_mode",
                parameters=params,
                result="success",
                error="Demo mode - mock response"
            )
            
            return {
                'partners': [],
                'demo_mode': True
            }

        name = params.get('name', '')
        limit = params.get('limit', 10)

        domain = []
        if name:
            domain.append(['name', 'ilike', name])

        partners = MCPServerHandler.odoo.execute(
            'res.partner',
            'search_read',
            [domain],
            ['name', 'email', 'phone', 'vat'],
            limit=limit
        )

        logger.info(f"Found {len(partners)} partners")
        
        log_action(
            action_type="search_partner",
            actor="odoo_mcp",
            target="res.partner",
            parameters=params,
            result="success"
        )

        return {
            'partners': partners
        }

    def health_check(self, params: Dict) -> Dict:
        """Check server health."""
        if MCPServerHandler.odoo and MCPServerHandler.odoo.is_connected():
            return {
                'status': 'healthy',
                'odoo_connected': True,
                'demo_mode': False
            }
        else:
            return {
                'status': 'degraded',
                'odoo_connected': False,
                'demo_mode': MCPServerHandler.demo_mode
            }

    def get_version(self, params: Dict) -> Dict:
        """Get server version."""
        return {
            'version': '1.0.0',
            'server': 'odoo_mcp',
            'retry_enabled': True
        }


# ============================================================================
# Main Server
# ============================================================================

def run_server():
    """Start the MCP server."""
    logger.info("=" * 60)
    logger.info("ODOO MCP SERVER (with retry handler) starting...")
    logger.info("=" * 60)
    logger.info(f"Host: {MCP_HOST}")
    logger.info(f"Port: {MCP_PORT}")
    logger.info(f"Odoo: {ODOO_HOST}:{ODOO_PORT}")
    logger.info(f"Max retries: {MAX_RETRIES}")
    logger.info("=" * 60)

    # Initialize Odoo connection
    odoo = OdooConnection(ODOO_HOST, ODOO_PORT, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
    
    # Try to connect
    try:
        if odoo.authenticate():
            logger.info("Odoo connection established")
            MCPServerHandler.odoo = odoo
            MCPServerHandler.demo_mode = False
        else:
            logger.warning("Odoo authentication failed - entering demo mode")
            MCPServerHandler.demo_mode = True
    except Exception as e:
        logger.warning(f"Odoo connection failed: {e} - entering demo mode")
        MCPServerHandler.demo_mode = True

    # Start HTTP server
    server = HTTPServer((MCP_HOST, MCP_PORT), MCPServerHandler)
    
    logger.info(f"Server running at http://{MCP_HOST}:{MCP_PORT}")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping server...")
        server.shutdown()
        
        # Log final health status
        health = get_system_health()
        logger.info(f"Final health: {health['summary']['success_rate']:.1f}% success rate")


if __name__ == "__main__":
    run_server()
