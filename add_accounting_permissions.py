#!/usr/bin/env python3
"""Add accounting permissions to odoo_user."""

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
    
    # Find odoo_user - Odoo 19 requires [[[domain]]]
    users = objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.users', 'search',
        [[['login', '=', 'odoo_user']]]
    )
    
    if not users:
        print("odoo_user not found")
        return
    
    user_id = users[0]
    print(f"Found odoo_user: id={user_id}")
    
    # Read user details
    user = objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.users', 'read',
        [user_id]
    )[0]
    print(f"User: {user['name']}")
    
    # Find accounting groups
    groups = objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.groups', 'search',
        [[['full_name', 'ilike', 'Accounting']]]
    )
    
    print(f"\nFound accounting groups: {groups}")
    
    # Get current groups
    current_group_ids = user.get('groups_id', [])
    print(f"Current groups: {current_group_ids}")
    
    # Add accounting groups
    new_group_ids = list(set(current_group_ids + groups))
    print(f"New groups: {new_group_ids}")
    
    # Update user - Odoo 19: write takes [ids, values_dict]
    objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.users', 'write',
        [user_id, {'groups_id': [(6, 0, new_group_ids)]}]
    )
    
    print(f"\nUpdated odoo_user with accounting permissions")
    
    # Verify
    user = objects.execute_kw(
        DB, uid, ADMIN_PASSWORD,
        'res.users', 'read',
        [user_id]
    )[0]
    
    print(f"Updated groups: {user.get('groups_id', [])}")

if __name__ == "__main__":
    main()
