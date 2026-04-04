#!/usr/bin/env python3
"""Create Odoo user for MCP integration."""

import xmlrpc.client

ODOO_URL = "http://localhost:8069"
DB = "odoo_db"
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "admin"

def main():
    # Authenticate as admin
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, ADMIN_LOGIN, ADMIN_PASSWORD, {})
    
    if not uid:
        print("Failed to authenticate as admin")
        return
    
    print(f"Authenticated as admin, uid={uid}")
    
    # Get object proxy
    objects = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    
    # Check if user exists
    existing = objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.users', 'search', [[['login', '=', 'odoo_user']]]
    )
    
    if existing:
        print(f"User already exists with ID: {existing[0]}")
        # Update password
        objects.execute_kw(
            DB, uid, ADMIN_PASSWORD,
            'res.users', 'write', [existing[0], {'password': 'odoo_secure_pass_2026'}]
        )
        print("Password updated")
    else:
        # Create user
        user_vals = {
            'name': 'Odoo MCP User',
            'login': 'odoo_user',
            'password': 'odoo_secure_pass_2026',
            'email': 'odoo_mcp@localhost',
        }
        
        # Create in res.partner first
        partner_id = objects.execute_kw(
            DB, uid, ADMIN_PASSWORD,
            'res.partner', 'create', [{'name': 'Odoo MCP User'}]
        )
        user_vals['partner_id'] = partner_id
        
        user_id = objects.execute_kw(
            DB, uid, ADMIN_PASSWORD,
            'res.users', 'create', [user_vals]
        )
        print(f"Created user with ID: {user_id}")
    
    # Test authentication
    test_uid = common.authenticate(DB, 'odoo_user', 'odoo_secure_pass_2026', {})
    if test_uid:
        print(f"SUCCESS: odoo_user authenticated with uid={test_uid}")
    else:
        print("FAILED: odoo_user authentication failed")

if __name__ == "__main__":
    main()
