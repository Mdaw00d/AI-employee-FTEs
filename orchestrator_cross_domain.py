#!/usr/bin/env python3
"""
Orchestrator Cross-Domain Integration Module
=============================================
Adds cross-domain awareness to the orchestrator by integrating:
- Domain classification
- Cross-domain routing
- Comprehensive audit trail

This module is imported by orchestrator.py to enhance its capabilities.

Usage:
    # In orchestrator.py, add:
    from orchestrator_cross_domain import CrossDomainIntegration
    
    # Initialize
    cross_domain = CrossDomainIntegration()
    
    # Use in task processing
    domain_info = cross_domain.classify_task(content, source)
    cross_domain.log_task_event("task_started", task_file)
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Import our new modules
from domain_classifier import DomainClassifier, Domain, get_domain_metadata
from cross_domain_router import CrossDomainRouter, get_router
from audit_trail import AuditTrail, AuditEventType, get_audit, log_audit_event

# Configuration
LOGS_DIR = "./Logs"
NEEDS_ACTION_DIR = "./Needs_Action"
DONE_DIR = "./Done"

# Ensure domain-specific directories exist
for domain in ['Personal', 'Business', 'Mixed']:
    os.makedirs(os.path.join(NEEDS_ACTION_DIR, domain), exist_ok=True)
    os.makedirs(os.path.join(DONE_DIR, domain), exist_ok=True)

# Setup logging
logger = logging.getLogger(__name__)


class CrossDomainIntegration:
    """
    Integrates cross-domain capabilities into the orchestrator.
    
    Provides:
    - Domain classification for incoming tasks
    - Domain-aware task routing
    - Comprehensive audit logging
    - Cross-domain action coordination
    """

    def __init__(self):
        self.classifier = DomainClassifier()
        self.router = CrossDomainRouter()
        self.audit = AuditTrail()
        
        # Track domain statistics
        self.domain_stats = {
            'personal': {'processed': 0, 'success': 0, 'failed': 0},
            'business': {'processed': 0, 'success': 0, 'failed': 0},
            'mixed': {'processed': 0, 'success': 0, 'failed': 0},
            'unknown': {'processed': 0, 'success': 0, 'failed': 0}
        }
        
        logger.info("Cross-Domain Integration initialized")
        
        # Log system start
        self.audit.log_event(
            event_type=AuditEventType.SYSTEM_START,
            actor="orchestrator_cross_domain",
            domain="system",
            result="success",
            metadata={"version": "1.0.0"}
        )

    def classify_task(self, content: str, source: str = None) -> Dict:
        """
        Classify a task and return domain metadata.
        
        Args:
            content: Task content
            source: Source identifier (e.g., 'gmail', 'facebook')
            
        Returns:
            Dict with domain classification and routing info
        """
        metadata = self.classifier.create_domain_metadata(content, source)
        
        # Log classification event
        self.audit.log_event(
            event_type=AuditEventType.DOMAIN_CLASSIFIED,
            actor="domain_classifier",
            domain=metadata['domain'],
            target=source or "unknown",
            result="success",
            metadata={
                'confidence': metadata['domain_confidence'],
                'keywords': metadata.get('keywords_detected', [])
            }
        )
        
        return metadata

    def route_task(self, task: Dict) -> Dict:
        """
        Route a task through the cross-domain router.
        
        Args:
            task: Task dict with domain, action, params
            
        Returns:
            Router result dict
        """
        # Update stats
        domain = task.get('domain', 'unknown')
        if domain in self.domain_stats:
            self.domain_stats[domain]['processed'] += 1
        
        # Log routing event
        self.audit.log_event(
            event_type=AuditEventType.DOMAIN_ROUTED,
            actor="cross_domain_router",
            domain=domain,
            action=task.get('action', 'unknown'),
            result="routed"
        )
        
        # Route through router
        result = self.router.route_task(task)
        
        # Log result
        if result.get('success'):
            self.domain_stats.get(domain, {}).get('success', 0)
            self.audit.log_event(
                event_type=AuditEventType.MCP_SUCCESS,
                actor="cross_domain_router",
                domain=domain,
                result="success",
                duration_ms=result.get('execution_time_ms')
            )
        else:
            self.domain_stats.get(domain, {}).get('failed', 0)
            self.audit.log_event(
                event_type=AuditEventType.MCP_FAILURE,
                actor="cross_domain_router",
                domain=domain,
                result="failure",
                error=result.get('error', 'Unknown error')
            )
        
        return result

    def log_task_event(
        self,
        event_type: str,
        task_file: str,
        domain: str = None,
        metadata: Dict = None
    ):
        """
        Log a task-related event to audit trail.
        
        Args:
            event_type: Type of event
            task_file: Task filename
            domain: Domain context
            metadata: Additional metadata
        """
        self.audit.log_event(
            event_type=event_type,
            actor="orchestrator",
            domain=domain or "unknown",
            target=task_file,
            result="success",
            metadata=metadata
        )

    def process_with_domain_awareness(self, task_file: str, content: str) -> Dict:
        """
        Process a task with full domain awareness.
        
        This is the main entry point for domain-aware task processing.
        
        Args:
            task_file: Path to task file
            content: Task content
            
        Returns:
            Processing result dict
        """
        start_time = datetime.now()
        
        # Step 1: Classify the task
        domain_info = self.classify_task(content, source=self._extract_source(task_file))
        domain = domain_info['domain']
        
        logger.info(f"Task classified as {domain} domain (confidence: {domain_info['domain_confidence']:.2f})")
        
        # Step 2: Log task start
        self.log_task_event(
            event_type=AuditEventType.TASK_STARTED,
            task_file=task_file,
            domain=domain,
            metadata={
                'classification': domain_info,
                'routing': domain_info['routing']
            }
        )
        
        # Step 3: Determine action type from content
        action = self._detect_action_type(content)
        
        # Step 4: Route and execute
        task = {
            'domain': domain,
            'action': action,
            'params': self._extract_params(content),
            'priority': domain_info['routing']['priority'],
            'source_file': task_file
        }
        
        result = self.route_task(task)
        
        # Step 5: Log completion
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        if result.get('success'):
            self.log_task_event(
                event_type=AuditEventType.TASK_COMPLETED,
                task_file=task_file,
                domain=domain,
                metadata={
                    'duration_ms': int(duration_ms),
                    'action': action,
                    'task_id': result.get('task_id')
                }
            )
        else:
            self.log_task_event(
                event_type=AuditEventType.TASK_FAILED,
                task_file=task_file,
                domain=domain,
                metadata={
                    'error': result.get('error'),
                    'duration_ms': int(duration_ms)
                }
            )
        
        return {
            'success': result.get('success', False),
            'domain': domain,
            'domain_info': domain_info,
            'result': result,
            'duration_ms': int(duration_ms)
        }

    def _extract_source(self, task_file: str) -> str:
        """Extract source identifier from task filename."""
        filename = os.path.basename(task_file).lower()
        
        if filename.startswith('fb_') or filename.startswith('facebook_'):
            return 'facebook'
        elif filename.startswith('ig_') or filename.startswith('instagram_'):
            return 'instagram'
        elif filename.startswith('x_') or filename.startswith('twitter_'):
            return 'x'
        elif filename.startswith('email_') or filename.startswith('gmail_'):
            return 'email'
        elif filename.startswith('linkedin_'):
            return 'linkedin'
        elif filename.startswith('whatsapp_'):
            return 'whatsapp'
        elif filename.startswith('accounting_') or filename.startswith('invoice_'):
            return 'odoo'
        else:
            return 'unknown'

    def _detect_action_type(self, content: str) -> str:
        """Detect action type from content."""
        content_lower = content.lower()
        
        # Invoice/Accounting actions
        if 'invoice' in content_lower or 'create invoice' in content_lower:
            return 'create_invoice'
        elif 'payment' in content_lower and 'register' in content_lower:
            return 'register_payment'
        
        # Email actions
        if 'send email' in content_lower or 'reply' in content_lower:
            return 'send_email'
        elif 'draft' in content_lower:
            return 'create_draft'
        
        # Social media actions
        if 'post' in content_lower:
            if 'facebook' in content_lower:
                return 'post_facebook'
            elif 'instagram' in content_lower:
                return 'post_instagram'
            elif 'twitter' in content_lower or 'x ' in content_lower:
                return 'post_x'
            elif 'linkedin' in content_lower:
                return 'post_linkedin'
            else:
                return 'post_social'
        
        # Cross-domain composite actions
        if 'invoice' in content_lower and ('email' in content_lower or 'notify' in content_lower):
            return 'invoice_and_notify'
        
        if 'social' in content_lower and 'email' in content_lower:
            return 'social_and_email'
        
        # Default to browser action
        return 'navigate'

    def _extract_params(self, content: str) -> Dict:
        """Extract parameters from content."""
        params = {}
        
        # Extract key-value pairs from markdown-style content
        import re
        
        # Pattern: **Key**: Value or Key: Value
        patterns = [
            r'\*\*([^*]+)\*\*:\s*(.+)',
            r'^([^:]+):\s*(.+)$'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for key, value in matches:
                key_clean = key.strip().lower().replace(' ', '_')
                params[key_clean] = value.strip()
        
        # Extract monetary values
        money_matches = re.findall(r'\$?[\d,]+\.?\d*', content)
        if money_matches:
            try:
                params['amount'] = float(money_matches[0].replace('$', '').replace(',', ''))
            except:
                pass
        
        # Extract email addresses
        email_matches = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', content)
        if email_matches:
            params['email'] = email_matches[0]
        
        return params

    def get_domain_statistics(self) -> Dict:
        """Get domain processing statistics."""
        total = sum(s['processed'] for s in self.domain_stats.values())
        success = sum(s['success'] for s in self.domain_stats.values())
        failed = sum(s['failed'] for s in self.domain_stats.values())
        
        return {
            'total_processed': total,
            'total_success': success,
            'total_failed': failed,
            'success_rate': (success / max(total, 1)) * 100,
            'by_domain': self.domain_stats,
            'timestamp': datetime.now().isoformat()
        }

    def export_audit_report(self, output_path: str = None) -> str:
        """Export comprehensive audit report."""
        return self.audit.export_audit_trail(output_path)

    def get_mcp_server_status(self) -> Dict:
        """Get status of all MCP servers."""
        return self.router.get_server_status()


# Global integration instance
_integration = None


def get_integration() -> CrossDomainIntegration:
    """Get or create the global integration instance."""
    global _integration
    if _integration is None:
        _integration = CrossDomainIntegration()
    return _integration


# Convenience functions for direct use
def classify_and_process(task_file: str) -> Dict:
    """Classify and process a task with domain awareness."""
    with open(task_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    integration = get_integration()
    return integration.process_with_domain_awareness(task_file, content)


def get_status() -> Dict:
    """Get cross-domain integration status."""
    integration = get_integration()
    return {
        'status': 'online',
        'mcp_servers': integration.get_mcp_server_status(),
        'statistics': integration.get_domain_statistics()
    }


if __name__ == "__main__":
    # Test the integration
    print("Testing Cross-Domain Integration...")
    print("=" * 60)
    
    integration = CrossDomainIntegration()
    
    # Test classification
    print("\nTesting domain classification...")
    test_contents = [
        ("Invoice for client ABC - $5000", "email"),
        ("Hey! Lunch this weekend?", "gmail"),
        ("URGENT: Customer complaint", "email"),
    ]
    
    for content, source in test_contents:
        result = integration.classify_task(content, source)
        print(f"\nContent: {content}")
        print(f"Domain: {result['domain']} (confidence: {result['domain_confidence']:.2f})")
        print(f"Priority: {result['routing']['priority']}")
    
    # Get statistics
    print("\n" + "=" * 60)
    print("Domain Statistics:")
    stats = integration.get_domain_statistics()
    print(f"Total processed: {stats['total_processed']}")
    print(f"Success rate: {stats['success_rate']:.1f}%")
    
    # Get MCP status
    print("\nMCP Server Status:")
    mcp_status = integration.get_mcp_server_status()
    for server, online in mcp_status.items():
        icon = "✅" if online else "❌"
        print(f"  {icon} {server}: {'Online' if online else 'Offline'}")
    
    print("\n" + "=" * 60)
    print("Cross-Domain Integration test complete!")
