#!/usr/bin/env python3
"""
Comprehensive Audit Trail System
=================================
Provides centralized audit logging for all system actions across domains.
Supports JSONL logging, querying, export, and compliance reporting.

Features:
- Immutable audit log entries (append-only)
- Comprehensive action tracking
- Domain-separated logging
- Query and filter capabilities
- Export for compliance/auditing
- Daily rotation with archival

Usage:
    from audit_trail import AuditTrail, AuditEvent
    
    audit = AuditTrail()
    
    # Log an event
    audit.log_event(
        event_type="task_completed",
        actor="orchestrator",
        domain="business",
        action="create_invoice",
        target="INV-2026-001",
        result="success",
        metadata={"amount": 5000.00, "customer": "ABC Corp"}
    )
    
    # Query events
    events = audit.query(domain="business", event_type="task_completed")
    
    # Export for compliance
    audit.export_audit_trail("audit_2026-04-02.json")
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from enum import Enum
import threading

# Configuration
LOGS_DIR = "./Logs"
AUDIT_DIR = os.path.join(LOGS_DIR, "Audit")
os.makedirs(AUDIT_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'audit_trail.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Standard audit event types."""
    # Task events
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_SKIPPED = "task_skipped"
    
    # Domain events
    DOMAIN_CLASSIFIED = "domain_classified"
    DOMAIN_ROUTED = "domain_routed"
    CROSS_DOMAIN_ACTION = "cross_domain_action"
    
    # MCP events
    MCP_CALL = "mcp_call"
    MCP_SUCCESS = "mcp_success"
    MCP_FAILURE = "mcp_failure"
    MCP_SERVER_ONLINE = "mcp_server_online"
    MCP_SERVER_OFFLINE = "mcp_server_offline"
    
    # Approval events
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_TIMEOUT = "approval_timeout"
    
    # Authentication events
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    AUTH_FAILED = "auth_failed"
    PERMISSION_DENIED = "permission_denied"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    CONFIG_CHANGED = "config_changed"
    ERROR_OCCURRED = "error_occurred"
    WARNING_RAISED = "warning_raised"
    
    # Data events
    DATA_CREATED = "data_created"
    DATA_READ = "data_read"
    DATA_UPDATED = "data_updated"
    DATA_DELETED = "data_deleted"
    
    # Financial events (for compliance)
    INVOICE_CREATED = "invoice_created"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_SENT = "payment_sent"
    FINANCIAL_ADJUSTMENT = "financial_adjustment"


class AuditTrail:
    """
    Comprehensive audit trail system with immutable logging.
    
    Features:
    - Append-only JSONL logs
    - Cryptographic chaining for integrity
    - Daily log rotation
    - Query and filter capabilities
    - Export for compliance
    """

    def __init__(self, enable_chaining: bool = True):
        """
        Initialize audit trail.
        
        Args:
            enable_chaining: If True, each entry includes hash of previous entry
        """
        self.enable_chaining = enable_chaining
        self.current_file: Optional[str] = None
        self.previous_hash: Optional[str] = None
        self.lock = threading.Lock()
        self.entry_count = 0
        
        # Initialize today's audit file
        self._rotate_log_if_needed()
        
        logger.info("Audit Trail initialized")

    def _get_today_file(self) -> str:
        """Get the audit log file path for today."""
        today = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(AUDIT_DIR, f"audit_{today}.jsonl")

    def _rotate_log_if_needed(self):
        """Rotate to new log file if date changed."""
        today_file = self._get_today_file()
        
        if self.current_file != today_file:
            self.current_file = today_file
            self.previous_hash = None
            self.entry_count = 0
            
            # Write header entry
            self._write_header()
            
            logger.info(f"Rotated audit log to {today_file}")

    def _write_header(self):
        """Write header entry for new log file."""
        header_entry = {
            '_version': '1.0',
            '_type': 'header',
            '_timestamp': datetime.now().isoformat(),
            '_date': datetime.now().strftime('%Y-%m-%d'),
            '_system': 'AI Employee System - Gold Tier',
            '_description': 'Comprehensive Audit Trail'
        }
        
        with open(self.current_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header_entry) + '\n')

    def _compute_hash(self, entry: Dict) -> str:
        """Compute SHA-256 hash of entry."""
        # Create deterministic JSON string, excluding hash fields and internal metadata
        exclude_prefixes = ('_hash', '_id', '_previous_hash', '_sequence')
        entry_copy = {
            k: v for k, v in entry.items() 
            if not any(k.startswith(p) for p in exclude_prefixes)
        }
        entry_str = json.dumps(entry_copy, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(entry_str.encode('utf-8')).hexdigest()

    def log_event(
        self,
        event_type: Union[AuditEventType, str],
        actor: str,
        domain: str = "unknown",
        action: str = None,
        target: str = None,
        result: str = None,
        metadata: Dict = None,
        error: str = None,
        duration_ms: int = None,
        user_id: str = None,
        session_id: str = None,
        ip_address: str = None
    ) -> str:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event (use AuditEventType enum)
            actor: Component/service performing the action
            domain: Domain context (personal, business, mixed)
            action: Specific action performed
            target: Target of the action
            result: Outcome (success, failure, skipped, etc.)
            metadata: Additional context data
            error: Error message if failed
            duration_ms: Action duration in milliseconds
            user_id: Associated user ID
            session_id: Session identifier
            ip_address: Source IP address
            
        Returns:
            Entry ID (hash of entry)
        """
        with self.lock:
            # Rotate if needed
            self._rotate_log_if_needed()
            
            # Build entry
            entry = {
                '_timestamp': datetime.now().isoformat(),
                '_sequence': self.entry_count,
                '_event_type': event_type.value if isinstance(event_type, AuditEventType) else event_type,
                '_actor': actor,
                '_domain': domain,
            }
            
            # Add optional fields
            if action:
                entry['_action'] = action
            if target:
                entry['_target'] = target
            if result:
                entry['_result'] = result
            if metadata:
                entry['metadata'] = metadata
            if error:
                entry['_error'] = error
            if duration_ms is not None:
                entry['_duration_ms'] = duration_ms
            if user_id:
                entry['_user_id'] = user_id
            if session_id:
                entry['_session_id'] = session_id
            if ip_address:
                entry['_ip_address'] = ip_address
            
            # Add cryptographic chaining
            if self.enable_chaining and self.previous_hash:
                entry['_previous_hash'] = self.previous_hash
            
            # Compute entry hash
            entry_hash = self._compute_hash(entry)
            entry['_hash'] = entry_hash
            entry['_id'] = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{self.entry_count:06d}"
            
            # Update previous hash for next entry
            self.previous_hash = entry_hash
            self.entry_count += 1
            
            # Write to file
            try:
                with open(self.current_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry) + '\n')
                
                logger.debug(f"Audit event logged: {entry['_id']} - {entry['_event_type']}")
                return entry['_id']
                
            except Exception as e:
                logger.error(f"Failed to write audit entry: {e}")
                return None

    def query(
        self,
        date: str = None,
        event_type: str = None,
        actor: str = None,
        domain: str = None,
        result: str = None,
        target: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Query audit trail entries.
        
        Args:
            date: Date string (YYYY-MM-DD), defaults to today
            event_type: Filter by event type
            actor: Filter by actor
            domain: Filter by domain
            result: Filter by result
            target: Filter by target
            start_time: Start timestamp (ISO format)
            end_time: End timestamp (ISO format)
            limit: Maximum entries to return
            
        Returns:
            List of matching audit entries
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        audit_file = os.path.join(AUDIT_DIR, f"audit_{date}.jsonl")
        
        if not os.path.exists(audit_file):
            logger.warning(f"Audit file not found: {audit_file}")
            return []
        
        results = []
        
        try:
            with open(audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        
                        # Skip header
                        if entry.get('_type') == 'header':
                            continue
                        
                        # Apply filters
                        if event_type and entry.get('_event_type') != event_type:
                            continue
                        if actor and entry.get('_actor') != actor:
                            continue
                        if domain and entry.get('_domain') != domain:
                            continue
                        if result and entry.get('_result') != result:
                            continue
                        if target and entry.get('_target') != target:
                            continue
                        
                        # Time range filter
                        entry_time = entry.get('_timestamp', '')
                        if start_time and entry_time < start_time:
                            continue
                        if end_time and entry_time > end_time:
                            continue
                        
                        results.append(entry)
                        
                        if len(results) >= limit:
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            logger.error(f"Error reading audit file: {e}")
        
        return results

    def get_events_by_id(self, entry_id: str, date: str = None) -> Optional[Dict]:
        """Get a specific event by ID."""
        events = self.query(date=date, limit=10000)
        for event in events:
            if event.get('_id') == entry_id:
                return event
        return None

    def verify_integrity(self, date: str = None) -> Dict:
        """
        Verify cryptographic integrity of audit log.
        
        Args:
            date: Date to verify (YYYY-MM-DD)
            
        Returns:
            Dict with verification results
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        audit_file = os.path.join(AUDIT_DIR, f"audit_{date}.jsonl")
        
        if not os.path.exists(audit_file):
            return {
                'valid': False,
                'error': 'Audit file not found'
            }
        
        entries = []
        previous_hash = None
        errors = []
        
        try:
            with open(audit_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        entry = json.loads(line.strip())
                        
                        # Skip header
                        if entry.get('_type') == 'header':
                            continue
                        
                        # Verify chain
                        stored_previous = entry.get('_previous_hash')
                        if previous_hash and stored_previous != previous_hash:
                            errors.append({
                                'line': line_num,
                                'entry_id': entry.get('_id'),
                                'error': 'Chain broken - previous hash mismatch'
                            })
                        
                        # Verify entry hash
                        stored_hash = entry.get('_hash')
                        entry_copy = {k: v for k, v in entry.items() if not k.startswith('_hash')}
                        computed_hash = self._compute_hash(entry_copy)
                        
                        if stored_hash != computed_hash:
                            errors.append({
                                'line': line_num,
                                'entry_id': entry.get('_id'),
                                'error': 'Entry hash mismatch - possible tampering'
                            })
                        
                        previous_hash = stored_hash
                        entries.append(entry)
                        
                    except json.JSONDecodeError as e:
                        errors.append({
                            'line': line_num,
                            'error': f'Invalid JSON: {str(e)}'
                        })
        
        except Exception as e:
            return {
                'valid': False,
                'error': str(e)
            }
        
        return {
            'valid': len(errors) == 0,
            'total_entries': len(entries),
            'errors': errors,
            'file': audit_file
        }

    def export_audit_trail(
        self,
        output_path: str = None,
        start_date: str = None,
        end_date: str = None,
        format: str = 'json'
    ) -> str:
        """
        Export audit trail for compliance/archival.
        
        Args:
            output_path: Output file path
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            format: Export format ('json' or 'csv')
            
        Returns:
            Path to exported file
        """
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = os.path.join(LOGS_DIR, f"audit_export_{timestamp}.{format}")
        
        # Collect entries from date range
        all_entries = []
        
        if start_date is None:
            start_date = datetime.now().strftime('%Y-%m-%d')
        if end_date is None:
            end_date = start_date
        
        # Parse dates
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Iterate through date range
        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            entries = self.query(date=date_str, limit=100000)
            all_entries.extend(entries)
            current += timedelta(days=1)
        
        # Export
        if format == 'json':
            export_data = {
                'exported_at': datetime.now().isoformat(),
                'start_date': start_date,
                'end_date': end_date,
                'total_entries': len(all_entries),
                'integrity_verified': self.verify_integrity(start_date)['valid'],
                'entries': all_entries
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
                
        elif format == 'csv':
            import csv
            
            if all_entries:
                fieldnames = list(all_entries[0].keys())
                
                with open(output_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_entries)
        
        logger.info(f"Exported {len(all_entries)} audit entries to {output_path}")
        return output_path

    def generate_compliance_report(
        self,
        report_type: str = 'daily',
        date: str = None,
        domain: str = None
    ) -> Dict:
        """
        Generate compliance summary report.
        
        Args:
            report_type: 'daily', 'weekly', 'monthly'
            date: Date for report (YYYY-MM-DD)
            domain: Filter by domain
            
        Returns:
            Dict with compliance summary
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        entries = self.query(date=date, limit=100000)
        
        if domain:
            entries = [e for e in entries if e.get('_domain') == domain]
        
        # Calculate statistics
        stats = {
            'total_events': len(entries),
            'by_type': {},
            'by_actor': {},
            'by_domain': {},
            'by_result': {},
            'errors': 0,
            'warnings': 0
        }
        
        for entry in entries:
            # Count by type
            event_type = entry.get('_event_type', 'unknown')
            stats['by_type'][event_type] = stats['by_type'].get(event_type, 0) + 1
            
            # Count by actor
            actor = entry.get('_actor', 'unknown')
            stats['by_actor'][actor] = stats['by_actor'].get(actor, 0) + 1
            
            # Count by domain
            domain_val = entry.get('_domain', 'unknown')
            stats['by_domain'][domain_val] = stats['by_domain'].get(domain_val, 0) + 1
            
            # Count by result
            result = entry.get('_result', 'unknown')
            stats['by_result'][result] = stats['by_result'].get(result, 0) + 1
            
            # Count errors
            if entry.get('_error'):
                stats['errors'] += 1
            if event_type == 'warning_raised':
                stats['warnings'] += 1
        
        return {
            'report_type': report_type,
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'statistics': stats,
            'integrity_status': self.verify_integrity(date)
        }

    def get_audit_summary(self, days: int = 7) -> Dict:
        """
        Get summary of audit activity for past N days.
        
        Args:
            days: Number of days to summarize
            
        Returns:
            Summary dict
        """
        summary = {
            'period_days': days,
            'generated_at': datetime.now().isoformat(),
            'daily_totals': {},
            'top_actors': {},
            'top_event_types': {},
            'error_rate': 0,
            'total_events': 0
        }
        
        total_events = 0
        total_errors = 0
        all_actors = {}
        all_types = {}
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            entries = self.query(date=date, limit=10000)
            
            daily_count = len(entries)
            summary['daily_totals'][date] = daily_count
            total_events += daily_count
            
            for entry in entries:
                actor = entry.get('_actor', 'unknown')
                all_actors[actor] = all_actors.get(actor, 0) + 1
                
                event_type = entry.get('_event_type', 'unknown')
                all_types[event_type] = all_types.get(event_type, 0) + 1
                
                if entry.get('_error'):
                    total_errors += 1
        
        summary['total_events'] = total_events
        summary['error_rate'] = (total_errors / max(total_events, 1)) * 100
        summary['top_actors'] = dict(sorted(all_actors.items(), key=lambda x: -x[1])[:10])
        summary['top_event_types'] = dict(sorted(all_types.items(), key=lambda x: -x[1])[:10])
        
        return summary


# Global audit instance
_audit = None


def get_audit() -> AuditTrail:
    """Get or create the global audit instance."""
    global _audit
    if _audit is None:
        _audit = AuditTrail()
    return _audit


def log_audit_event(**kwargs) -> str:
    """Convenience function to log an audit event."""
    return get_audit().log_event(**kwargs)


def query_audit(**kwargs) -> List[Dict]:
    """Convenience function to query audit trail."""
    return get_audit().query(**kwargs)


if __name__ == "__main__":
    # Test the audit trail
    print("Testing Audit Trail System...")
    print("=" * 60)
    
    audit = AuditTrail()
    
    # Log test events
    print("\nLogging test events...")
    
    audit.log_event(
        event_type=AuditEventType.SYSTEM_START,
        actor="audit_trail",
        domain="business",
        result="success"
    )
    
    audit.log_event(
        event_type=AuditEventType.TASK_CREATED,
        actor="orchestrator",
        domain="business",
        action="create_invoice",
        target="INV-2026-001",
        result="success",
        metadata={"amount": 5000.00, "customer": "ABC Corp"}
    )
    
    audit.log_event(
        event_type=AuditEventType.DOMAIN_CLASSIFIED,
        actor="domain_classifier",
        domain="business",
        target="email_001",
        result="success",
        metadata={"confidence": 0.95, "keywords": ["invoice", "payment"]}
    )
    
    audit.log_event(
        event_type=AuditEventType.MCP_CALL,
        actor="cross_domain_router",
        domain="business",
        action="create_invoice",
        target="odoo",
        result="success",
        duration_ms=234
    )
    
    audit.log_event(
        event_type=AuditEventType.TASK_FAILED,
        actor="email_sender",
        domain="personal",
        action="send_email",
        target="friend@example.com",
        result="failure",
        error="SMTP connection timeout"
    )
    
    print("Events logged!")
    
    # Query events
    print("\nQuerying business domain events...")
    business_events = audit.query(domain="business", limit=10)
    print(f"Found {len(business_events)} business events")
    
    # Verify integrity
    print("\nVerifying audit log integrity...")
    integrity = audit.verify_integrity()
    print(f"Integrity valid: {integrity['valid']}")
    if integrity.get('errors'):
        print(f"Errors: {integrity['errors']}")
    
    # Generate summary
    print("\nGenerating audit summary...")
    summary = audit.get_audit_summary(days=1)
    print(f"Total events: {summary['total_events']}")
    print(f"Error rate: {summary['error_rate']:.2f}%")
    
    # Generate compliance report
    print("\nGenerating compliance report...")
    report = audit.generate_compliance_report(report_type='daily')
    print(f"Report generated: {report['generated_at']}")
    print(f"Statistics: {json.dumps(report['statistics'], indent=2)}")
    
    print("\n" + "=" * 60)
    print("Audit Trail System test complete!")
