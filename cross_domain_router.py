#!/usr/bin/env python3
"""
Cross-Domain MCP Router - Unified Task Routing System
======================================================
Routes tasks across different MCP servers based on domain classification,
enabling coordinated Personal + Business domain actions.

Features:
- Domain-aware task routing
- Multi-MCP coordination for complex tasks
- Cross-domain action chaining
- Unified response aggregation
- Audit trail for all routed actions

Usage:
    python cross_domain_router.py
    
    # Or import as module:
    from cross_domain_router import CrossDomainRouter
    
    router = CrossDomainRouter()
    result = router.route_task({
        'domain': 'business',
        'action': 'send_invoice_and_notify',
        'params': {...}
    })
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from enum import Enum
import urllib.request
import urllib.error

# Import domain classifier
from domain_classifier import DomainClassifier, Domain, get_domain_metadata

# Configuration
LOGS_DIR = "./Logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# MCP Server Configuration
MCP_SERVERS = {
    'email': {'host': 'localhost', 'port': 8000, 'url': 'http://localhost:8000/rpc'},
    'social': {'host': 'localhost', 'port': 8001, 'url': 'http://localhost:8001/rpc'},
    'browser': {'host': 'localhost', 'port': 8002, 'url': 'http://localhost:8002/rpc'},
    'odoo': {'host': 'localhost', 'port': 8070, 'url': 'http://localhost:8070/rpc'},
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'cross_domain_router.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class CrossDomainRouter:
    """
    Routes tasks across MCP servers with domain awareness.
    
    Supports:
    - Single-domain tasks (routed to appropriate MCP)
    - Cross-domain tasks (coordinated multi-MCP execution)
    - Action chaining (sequential dependent actions)
    - Parallel execution (independent actions)
    """

    def __init__(self):
        self.classifier = DomainClassifier()
        self.execution_history: List[Dict] = []
        self.mcp_status: Dict[str, bool] = {}
        
        # Check initial MCP server status
        self._check_mcp_servers()
        
        logger.info("Cross-Domain Router initialized")

    def _check_mcp_servers(self, timeout: int = 2):
        """Check status of all MCP servers."""
        for name, config in MCP_SERVERS.items():
            try:
                result = self._call_mcp(name, 'health_check', {}, timeout)
                self.mcp_status[name] = result.get('success', False)
            except Exception:
                self.mcp_status[name] = False
        
        logger.info(f"MCP Server Status: {self.mcp_status}")

    def _call_mcp(self, server_name: str, method: str, params: Dict = None, timeout: int = 30) -> Dict:
        """
        Call an MCP server via JSON-RPC.
        
        Args:
            server_name: Name of the MCP server
            method: RPC method to call
            params: Method parameters
            timeout: Request timeout in seconds
            
        Returns:
            Dict with result or error
        """
        if server_name not in MCP_SERVERS:
            return {'success': False, 'error': f'Unknown MCP server: {server_name}'}

        url = MCP_SERVERS[server_name]['url']
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": int(time.time() * 1000)
        }

        try:
            data = json.dumps(request).encode('utf-8')
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode('utf-8'))

                if 'error' in result:
                    return {
                        'success': False,
                        'error': result['error'].get('message', 'Unknown error'),
                        'server': server_name
                    }

                return {
                    'success': True,
                    'result': result.get('result', {}),
                    'server': server_name
                }

        except urllib.error.URLError as e:
            logger.warning(f"MCP {server_name} connection error: {e}")
            self.mcp_status[server_name] = False
            return {
                'success': False,
                'error': f'Connection error: {str(e)}',
                'server': server_name,
                'server_offline': True
            }
        except Exception as e:
            logger.warning(f"MCP {server_name} error: {e}")
            return {
                'success': False,
                'error': str(e),
                'server': server_name
            }

    def route_task(self, task: Dict) -> Dict:
        """
        Route a task to appropriate MCP server(s).
        
        Args:
            task: Dict with task definition:
                - domain: 'personal' | 'business' | 'mixed'
                - action: Action to perform
                - params: Action parameters
                - priority: Optional priority level
                - chain: Optional list of chained actions
                
        Returns:
            Dict with execution results
        """
        start_time = time.time()
        
        # Extract task components
        domain_str = task.get('domain', 'unknown')
        action = task.get('action', '')
        params = task.get('params', {})
        priority = task.get('priority', 'normal')
        chained_actions = task.get('chain', [])
        
        # Convert domain string to enum
        try:
            domain = Domain(domain_str)
        except ValueError:
            domain = Domain.UNKNOWN
        
        # Get routing rules for domain
        routing = self.classifier.get_routing_rules(domain)
        
        logger.info(f"Routing task: domain={domain.value}, action={action}, priority={priority}")
        
        # Create execution plan
        execution_plan = self._create_execution_plan(action, params, domain, routing)
        
        # Execute the plan
        if chained_actions:
            result = self._execute_chained_actions(execution_plan, chained_actions, domain)
        else:
            result = self._execute_single_action(execution_plan, domain)
        
        # Add metadata
        execution_time = time.time() - start_time
        result['execution_time_ms'] = int(execution_time * 1000)
        result['domain'] = domain.value
        result['task_id'] = self._generate_task_id()
        
        # Log to execution history
        self._log_execution(task, result)
        
        return result

    def _create_execution_plan(self, action: str, params: Dict, domain: Domain, routing: Dict) -> Dict:
        """Create execution plan based on action type and domain."""
        
        # Action to MCP server mapping
        action_mappings = {
            # Email actions
            'send_email': {'server': 'email', 'method': 'send_email'},
            'create_draft': {'server': 'email', 'method': 'create_draft'},
            'send_reply': {'server': 'email', 'method': 'send_reply'},
            
            # Social media actions
            'post_facebook': {'server': 'social', 'method': 'post_facebook'},
            'post_instagram': {'server': 'social', 'method': 'post_instagram'},
            'post_x': {'server': 'social', 'method': 'post_x'},
            'post_linkedin': {'server': 'social', 'method': 'post_linkedin'},
            'post_social': {'server': 'social', 'method': 'post_to_all'},
            
            # Accounting actions
            'create_invoice': {'server': 'odoo', 'method': 'create_invoice'},
            'register_payment': {'server': 'odoo', 'method': 'register_payment'},
            'get_transactions': {'server': 'odoo', 'method': 'get_transactions'},
            'search_partner': {'server': 'odoo', 'method': 'search_partner'},
            
            # Browser actions
            'navigate': {'server': 'browser', 'method': 'navigate'},
            'fill_form': {'server': 'browser', 'method': 'fill'},
            'click_element': {'server': 'browser', 'method': 'click'},
            'screenshot': {'server': 'browser', 'method': 'screenshot'},
            
            # Cross-domain composite actions
            'invoice_and_notify': {
                'parallel': [
                    {'server': 'odoo', 'method': 'create_invoice'},
                    {'server': 'email', 'method': 'send_email'}
                ]
            },
            'social_and_email': {
                'parallel': [
                    {'server': 'social', 'method': 'post_to_all'},
                    {'server': 'email', 'method': 'send_email'}
                ]
            },
            'full_campaign': {
                'sequential': [
                    {'server': 'odoo', 'method': 'get_transactions'},
                    {'server': 'social', 'method': 'post_to_all'},
                    {'server': 'email', 'method': 'send_email'}
                ]
            }
        }
        
        plan = {
            'action': action,
            'domain': domain,
            'routing': routing,
            'execution': action_mappings.get(action, {'server': 'browser', 'method': 'navigate'}),
            'params': params
        }
        
        return plan

    def _execute_single_action(self, plan: Dict, domain: Domain) -> Dict:
        """Execute a single action."""
        execution = plan['execution']
        params = plan['params']
        
        # Add domain context to params
        params['_domain'] = domain.value
        params['_priority'] = plan['routing']['priority']
        
        if 'parallel' in execution:
            return self._execute_parallel(execution['parallel'], params)
        elif 'sequential' in execution:
            return self._execute_sequential(execution['sequential'], params)
        else:
            return self._call_mcp(execution['server'], execution['method'], params)

    def _execute_parallel(self, actions: List[Dict], params: Dict) -> Dict:
        """Execute multiple actions in parallel."""
        results = []
        errors = []
        
        for action in actions:
            server = action['server']
            method = action['method']
            
            if not self.mcp_status.get(server, False):
                errors.append({
                    'server': server,
                    'error': f'Server {server} is offline'
                })
                continue
            
            result = self._call_mcp(server, method, params.copy())
            if result['success']:
                results.append(result)
            else:
                errors.append(result)
        
        return {
            'success': len(errors) == 0,
            'results': results,
            'errors': errors,
            'execution_type': 'parallel'
        }

    def _execute_sequential(self, actions: List[Dict], initial_params: Dict) -> Dict:
        """Execute multiple actions sequentially with result chaining."""
        results = []
        params = initial_params.copy()
        
        for i, action in enumerate(actions):
            server = action['server']
            method = action['method']
            
            if not self.mcp_status.get(server, False):
                return {
                    'success': False,
                    'error': f'Server {server} is offline at step {i + 1}',
                    'completed_steps': len(results),
                    'execution_type': 'sequential'
                }
            
            result = self._call_mcp(server, method, params)
            
            if not result['success']:
                return {
                    'success': False,
                    'error': result.get('error', f'Step {i + 1} failed'),
                    'completed_steps': len(results),
                    'results': results,
                    'execution_type': 'sequential'
                }
            
            results.append(result)
            
            # Chain results to next action's params
            if 'result' in result:
                params.update(result['result'])
        
        return {
            'success': True,
            'results': results,
            'total_steps': len(actions),
            'execution_type': 'sequential'
        }

    def _execute_chained_actions(self, initial_plan: Dict, chain: List[Dict], domain: Domain) -> Dict:
        """Execute a chain of actions with dependencies."""
        all_results = []
        
        # Execute initial action
        initial_result = self._execute_single_action(initial_plan, domain)
        
        if not initial_result['success']:
            return initial_result
        
        all_results.append({
            'step': 0,
            'action': initial_plan['action'],
            'result': initial_result
        })
        
        # Execute chained actions
        context = initial_result.get('result', {})
        
        for i, chain_item in enumerate(chain):
            chain_action = chain_item.get('action', '')
            chain_params = chain_item.get('params', {})
            
            # Merge context into params
            merged_params = {**context, **chain_params}
            
            plan = self._create_execution_plan(chain_action, merged_params, domain, initial_plan['routing'])
            result = self._execute_single_action(plan, domain)
            
            if not result['success']:
                return {
                    'success': False,
                    'error': f'Chain step {i + 1} failed: {result.get("error")}',
                    'completed_steps': len(all_results),
                    'results': all_results,
                    'execution_type': 'chained'
                }
            
            all_results.append({
                'step': i + 1,
                'action': chain_action,
                'result': result
            })
            
            # Update context for next step
            context.update(result.get('result', {}))
        
        return {
            'success': True,
            'results': all_results,
            'total_steps': len(all_results),
            'execution_type': 'chained'
        }

    def _log_execution(self, task: Dict, result: Dict):
        """Log execution to history and audit trail."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'task': task,
            'result': result,
            'domain': task.get('domain', 'unknown'),
            'priority': task.get('priority', 'normal')
        }
        
        self.execution_history.append(log_entry)
        
        # Keep only last 1000 executions in memory
        if len(self.execution_history) > 1000:
            self.execution_history = self.execution_history[-1000:]
        
        # Write to audit log
        self._write_audit_log(log_entry)

    def _write_audit_log(self, entry: Dict):
        """Write entry to comprehensive audit log."""
        audit_file = os.path.join(LOGS_DIR, f"audit_trail_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
        
        try:
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    def _generate_task_id(self) -> str:
        """Generate unique task ID."""
        return f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 10000}"

    def get_execution_history(self, limit: int = 100, domain: str = None) -> List[Dict]:
        """
        Get execution history.
        
        Args:
            limit: Maximum number of entries to return
            domain: Optional filter by domain
            
        Returns:
            List of execution history entries
        """
        history = self.execution_history[-limit:]
        
        if domain:
            history = [h for h in history if h.get('domain') == domain]
        
        return history

    def get_server_status(self) -> Dict:
        """Get current status of all MCP servers."""
        self._check_mcp_servers()
        return self.mcp_status

    def export_audit_trail(self, output_path: str = None, date: str = None) -> str:
        """
        Export audit trail to JSON file.
        
        Args:
            output_path: Optional output file path
            date: Optional date string (YYYY-MM-DD)
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            date_str = date or datetime.now().strftime('%Y-%m-%d')
            output_path = os.path.join(LOGS_DIR, f"audit_export_{date_str}.json")
        
        # Read audit log for specified date
        audit_file = os.path.join(LOGS_DIR, f"audit_trail_{date or datetime.now().strftime('%Y-%m-%d')}.jsonl")
        entries = []
        
        if os.path.exists(audit_file):
            with open(audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        
        # Export
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'source_file': audit_file,
            'total_entries': len(entries),
            'entries': entries
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported {len(entries)} audit entries to {output_path}")
        return output_path


# Global router instance
_router = None


def get_router() -> CrossDomainRouter:
    """Get or create the global router instance."""
    global _router
    if _router is None:
        _router = CrossDomainRouter()
    return _router


def route_task(task: Dict) -> Dict:
    """Convenience function to route a task."""
    return get_router().route_task(task)


if __name__ == "__main__":
    # Test the router
    print("Testing Cross-Domain Router...")
    print("=" * 60)
    
    router = CrossDomainRouter()
    
    print("\nMCP Server Status:")
    status = router.get_server_status()
    for server, online in status.items():
        icon = "✅" if online else "❌"
        print(f"  {icon} {server}: {'Online' if online else 'Offline'}")
    
    # Test task routing
    print("\n" + "=" * 60)
    print("Testing Task Routing...")
    
    test_tasks = [
        {
            'domain': 'business',
            'action': 'create_invoice',
            'params': {
                'partner_name': 'Test Corp',
                'amount': 1000.00,
                'description': 'Test Invoice'
            },
            'priority': 'high'
        },
        {
            'domain': 'personal',
            'action': 'send_email',
            'params': {
                'to': 'friend@example.com',
                'subject': 'Lunch Plans',
                'body': 'Hey! Want to grab lunch?'
            }
        },
        {
            'domain': 'business',
            'action': 'invoice_and_notify',
            'params': {
                'customer': 'ABC Corp',
                'amount': 5000.00,
                'notify_email': 'billing@abccorp.com'
            },
            'priority': 'critical'
        }
    ]
    
    for task in test_tasks:
        print(f"\nRouting task: {task['action']} ({task['domain']})")
        result = router.route_task(task)
        print(f"  Success: {result['success']}")
        print(f"  Execution Time: {result.get('execution_time_ms', 0)}ms")
        print(f"  Task ID: {result.get('task_id')}")
    
    print("\n" + "=" * 60)
    print("Cross-Domain Router test complete!")
