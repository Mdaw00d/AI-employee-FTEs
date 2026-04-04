#!/usr/bin/env python3
"""
Domain Classifier - Cross-Domain Integration System
====================================================
Classifies tasks and communications into Personal or Business domains,
and handles cross-domain routing for coordinated actions.

Domains:
- PERSONAL: Individual communications, personal social media, private emails
- BUSINESS: Company-related tasks, accounting, customer communications, official posts

Usage:
    from domain_classifier import DomainClassifier, Domain
    
    classifier = DomainClassifier()
    domain = classifier.classify_content("Invoice for client ABC")
    # Returns: Domain.BUSINESS
    
    routing = classifier.get_routing_rules(domain)
    # Returns domain-specific routing configuration
"""

import os
import re
import json
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Configuration
LOGS_DIR = "./Logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'domain_classifier.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Domain(Enum):
    """Domain types for classification."""
    PERSONAL = "personal"
    BUSINESS = "business"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class DomainClassifier:
    """
    Classifies content into Personal or Business domains.
    
    Uses keyword matching, context analysis, and source identification
    to determine the appropriate domain for routing and processing.
    """

    # Business-related keywords and patterns
    BUSINESS_KEYWORDS = [
        # Financial
        'invoice', 'payment', 'receipt', 'billing', 'accounting', 'tax', 'revenue',
        'expense', 'budget', 'financial', 'quarterly', 'fiscal', 'audit',
        
        # Business operations
        'client', 'customer', 'vendor', 'supplier', 'partner', 'stakeholder',
        'contract', 'agreement', 'proposal', 'tender', 'bid', 'rfp',
        'meeting', 'conference', 'presentation', 'report', 'briefing',
        
        # Sales & Marketing
        'sales', 'marketing', 'lead', 'prospect', 'conversion', 'pipeline',
        'campaign', 'brand', 'promotion', 'advertisement', 'pr',
        
        # HR & Operations
        'employee', 'hire', 'recruit', 'onboard', 'performance', 'review',
        'policy', 'procedure', 'compliance', 'regulation', 'governance',
        
        # Products & Services
        'product', 'service', 'delivery', 'fulfillment', 'inventory', 'stock',
        'order', 'purchase', 'procurement', 'supply chain',
        
        # Corporate communications
        'ceo', 'cfo', 'cto', 'executive', 'board', 'shareholder', 'investor',
        'company', 'corporation', 'llc', 'inc', 'ltd', 'enterprise'
    ]

    # Personal-related keywords and patterns
    PERSONAL_KEYWORDS = [
        # Personal life
        'family', 'friend', 'birthday', 'anniversary', 'wedding', 'party',
        'vacation', 'holiday', 'travel', 'trip', 'weekend', 'leisure',
        
        # Personal interests
        'hobby', 'game', 'movie', 'music', 'book', 'sport', 'fitness',
        'restaurant', 'food', 'recipe', 'cooking', 'shopping',
        
        # Personal communications
        'hey', 'hi', 'hello', 'thanks', 'love', 'miss', 'hope', 'wish',
        'personal', 'private', 'confidential', 'just checking',
        
        # Social (non-business)
        'follow', 'like', 'share', 'comment', 'dm', 'chat', 'catch up'
    ]

    # High-priority business indicators (strong signals)
    HIGH_PRIORITY_BUSINESS = [
        'urgent', 'asap', 'immediate', 'critical', 'emergency',
        'legal', 'lawsuit', 'compliance', 'regulatory',
        'breach', 'security', 'incident', 'crisis',
        'terminate', 'cancel', 'refund', 'complaint', 'dispute'
    ]

    # Source-based domain mapping
    SOURCE_DOMAIN_MAP = {
        # Business sources
        'linkedin': Domain.BUSINESS,
        'company_email': Domain.BUSINESS,
        'odoo': Domain.BUSINESS,
        'accounting': Domain.BUSINESS,
        'invoice': Domain.BUSINESS,
        'customer': Domain.BUSINESS,
        
        # Personal sources
        'personal_email': Domain.PERSONAL,
        'facebook_personal': Domain.PERSONAL,
        'instagram_personal': Domain.PERSONAL,
        'whatsapp_personal': Domain.PERSONAL,
        
        # Mixed sources (need content analysis)
        'facebook': Domain.MIXED,
        'instagram': Domain.MIXED,
        'twitter': Domain.MIXED,
        'x': Domain.MIXED,
        'gmail': Domain.MIXED,
        'email': Domain.MIXED,
    }

    def __init__(self, custom_rules: Dict = None):
        """
        Initialize the domain classifier.
        
        Args:
            custom_rules: Optional dict of custom classification rules
        """
        self.custom_rules = custom_rules or {}
        self.classification_history: List[Dict] = []
        
        # Load additional rules from config file if exists
        self._load_custom_rules()
        
        logger.info("Domain Classifier initialized")

    def _load_custom_rules(self):
        """Load custom classification rules from config file."""
        config_path = Path("./domain_rules.json")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    custom_config = json.load(f)
                    if 'business_keywords' in custom_config:
                        self.BUSINESS_KEYWORDS.extend(custom_config['business_keywords'])
                    if 'personal_keywords' in custom_config:
                        self.PERSONAL_KEYWORDS.extend(custom_config['personal_keywords'])
                    if 'source_mapping' in custom_config:
                        self.SOURCE_DOMAIN_MAP.update(custom_config['source_mapping'])
                logger.info("Loaded custom classification rules")
            except Exception as e:
                logger.warning(f"Failed to load custom rules: {e}")

    def classify_content(self, content: str, source: str = None) -> Domain:
        """
        Classify content into a domain.
        
        Args:
            content: The text content to classify
            source: Optional source identifier (e.g., 'gmail', 'linkedin')
            
        Returns:
            Domain enum value
        """
        if not content:
            return Domain.UNKNOWN

        # Check source-based classification first
        if source:
            source_domain = self._classify_by_source(source)
            if source_domain != Domain.MIXED and source_domain != Domain.UNKNOWN:
                result = source_domain
                self._log_classification(content, source, result, "source-based")
                return result

        # Score the content
        business_score = 0
        personal_score = 0
        high_priority_business = False

        content_lower = content.lower()

        # Check for high-priority business indicators
        for keyword in self.HIGH_PRIORITY_BUSINESS:
            if keyword in content_lower:
                high_priority_business = True
                business_score += 5

        # Count business keywords
        for keyword in self.BUSINESS_KEYWORDS:
            if keyword in content_lower:
                business_score += 1

        # Count personal keywords
        for keyword in self.PERSONAL_KEYWORDS:
            if keyword in content_lower:
                personal_score += 1

        # Check custom rules
        custom_result = self._apply_custom_rules(content, source)
        if custom_result:
            result = custom_result
            self._log_classification(content, source, result, "custom-rule")
            return result

        # Determine domain based on scores
        if high_priority_business:
            result = Domain.BUSINESS
        elif business_score > personal_score * 2:
            result = Domain.BUSINESS
        elif personal_score > business_score * 2:
            result = Domain.PERSONAL
        elif business_score > 0 or personal_score > 0:
            result = Domain.MIXED
        else:
            result = Domain.UNKNOWN

        self._log_classification(content, source, result, "keyword-analysis")
        return result

    def _classify_by_source(self, source: str) -> Domain:
        """Classify based on source identifier."""
        source_lower = source.lower()
        
        # Check direct mapping
        for key, domain in self.SOURCE_DOMAIN_MAP.items():
            if key in source_lower:
                return domain
        
        return Domain.UNKNOWN

    def _apply_custom_rules(self, content: str, source: str) -> Optional[Domain]:
        """Apply custom classification rules."""
        content_lower = content.lower()
        
        for rule in self.custom_rules.get('rules', []):
            if 'keywords' in rule:
                if any(kw in content_lower for kw in rule['keywords']):
                    return Domain(rule.get('domain', Domain.UNKNOWN.value))
        
        return None

    def _log_classification(self, content: str, source: str, result: Domain, method: str):
        """Log classification for audit trail."""
        self.classification_history.append({
            'timestamp': datetime.now().isoformat(),
            'content_preview': content[:100] if content else '',
            'source': source or 'unknown',
            'domain': result.value,
            'method': method
        })
        
        # Keep only last 1000 classifications in memory
        if len(self.classification_history) > 1000:
            self.classification_history = self.classification_history[-1000:]

    def get_routing_rules(self, domain: Domain) -> Dict:
        """
        Get routing rules for a specific domain.
        
        Args:
            domain: The domain to get routing rules for
            
        Returns:
            Dict with routing configuration
        """
        routing_config = {
            Domain.PERSONAL: {
                'priority': 'normal',
                'approval_required': False,
                'auto_execute': True,
                'log_level': 'standard',
                'mcp_servers': ['email', 'social'],
                'output_prefix': 'PERSONAL_',
                'directories': {
                    'input': './Needs_Action/Personal',
                    'output': './Done/Personal',
                    'approval': './Pending_Approval/Personal',
                    'logs': './Logs/Personal'
                }
            },
            Domain.BUSINESS: {
                'priority': 'high',
                'approval_required': True,
                'auto_execute': False,
                'log_level': 'comprehensive',
                'mcp_servers': ['email', 'social', 'odoo', 'browser'],
                'output_prefix': 'BUSINESS_',
                'directories': {
                    'input': './Needs_Action/Business',
                    'output': './Done/Business',
                    'approval': './Pending_Approval/Business',
                    'logs': './Logs/Business'
                }
            },
            Domain.MIXED: {
                'priority': 'normal',
                'approval_required': True,
                'auto_execute': False,
                'log_level': 'comprehensive',
                'mcp_servers': ['email', 'social', 'browser'],
                'output_prefix': 'MIXED_',
                'directories': {
                    'input': './Needs_Action/Mixed',
                    'output': './Done/Mixed',
                    'approval': './Pending_Approval/Mixed',
                    'logs': './Logs/Mixed'
                }
            },
            Domain.UNKNOWN: {
                'priority': 'low',
                'approval_required': True,
                'auto_execute': False,
                'log_level': 'standard',
                'mcp_servers': ['email', 'browser'],
                'output_prefix': 'UNKNOWN_',
                'directories': {
                    'input': './Needs_Action',
                    'output': './Done',
                    'approval': './Pending_Approval',
                    'logs': './Logs'
                }
            }
        }
        
        return routing_config.get(domain, routing_config[Domain.UNKNOWN])

    def create_domain_metadata(self, content: str, source: str = None) -> Dict:
        """
        Create metadata dict with domain classification info.
        
        Args:
            content: The content to analyze
            source: Optional source identifier
            
        Returns:
            Dict with domain metadata
        """
        domain = self.classify_content(content, source)
        routing = self.get_routing_rules(domain)
        
        return {
            'domain': domain.value,
            'domain_confidence': self._calculate_confidence(content, domain),
            'routing': {
                'priority': routing['priority'],
                'approval_required': routing['approval_required'],
                'auto_execute': routing['auto_execute']
            },
            'source': source or 'unknown',
            'classified_at': datetime.now().isoformat(),
            'keywords_detected': self._extract_detected_keywords(content)
        }

    def _calculate_confidence(self, content: str, domain: Domain) -> float:
        """Calculate confidence score for classification (0.0 to 1.0)."""
        content_lower = content.lower()
        
        if domain == Domain.UNKNOWN:
            return 0.0
        
        business_count = sum(1 for kw in self.BUSINESS_KEYWORDS if kw in content_lower)
        personal_count = sum(1 for kw in self.PERSONAL_KEYWORDS if kw in content_lower)
        total = business_count + personal_count
        
        if total == 0:
            return 0.3  # Low confidence when no keywords found
        
        if domain == Domain.BUSINESS:
            return min(1.0, business_count / max(total, 1))
        elif domain == Domain.PERSONAL:
            return min(1.0, personal_count / max(total, 1))
        else:
            return 0.5  # Mixed domain has medium confidence

    def _extract_detected_keywords(self, content: str) -> List[str]:
        """Extract keywords that were detected in content."""
        content_lower = content.lower()
        detected = []
        
        for kw in self.BUSINESS_KEYWORDS + self.PERSONAL_KEYWORDS + self.HIGH_PRIORITY_BUSINESS:
            if kw in content_lower:
                detected.append(kw)
        
        return detected[:20]  # Limit to 20 keywords

    def export_classification_log(self, filepath: str = None):
        """Export classification history to JSON file."""
        if filepath is None:
            filepath = os.path.join(LOGS_DIR, f"classification_log_{datetime.now().strftime('%Y%m%d')}.json")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'exported_at': datetime.now().isoformat(),
                    'total_classifications': len(self.classification_history),
                    'classifications': self.classification_history
                }, f, indent=2)
            logger.info(f"Exported classification log to {filepath}")
        except Exception as e:
            logger.error(f"Failed to export classification log: {e}")


# Global classifier instance for easy import
_classifier = None


def get_classifier() -> DomainClassifier:
    """Get or create the global classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = DomainClassifier()
    return _classifier


def classify(content: str, source: str = None) -> Domain:
    """Convenience function to classify content."""
    return get_classifier().classify_content(content, source)


def get_domain_metadata(content: str, source: str = None) -> Dict:
    """Convenience function to get domain metadata."""
    return get_classifier().create_domain_metadata(content, source)


if __name__ == "__main__":
    # Test the classifier
    print("Testing Domain Classifier...")
    print("=" * 60)
    
    classifier = DomainClassifier()
    
    test_cases = [
        ("Invoice #1234 for client ABC Corp - Payment due", "email"),
        ("Hey! Want to grab lunch this weekend?", "gmail"),
        ("URGENT: Customer complaint about delayed shipment", "email"),
        ("Happy birthday! Hope you have a great day!", "facebook"),
        ("Q3 financial report needs to be submitted by Friday", "email"),
        ("Thanks for the follow! Love your content", "instagram"),
        ("Board meeting scheduled for next Tuesday at 2pm", "linkedin"),
        ("Can you pick up groceries on your way home?", "whatsapp"),
    ]
    
    for content, source in test_cases:
        domain = classifier.classify_content(content, source)
        metadata = classifier.create_domain_metadata(content, source)
        print(f"\nContent: {content[:50]}...")
        print(f"Source: {source}")
        print(f"Domain: {domain.value}")
        print(f"Confidence: {metadata['domain_confidence']:.2f}")
        print(f"Priority: {metadata['routing']['priority']}")
        print(f"Approval Required: {metadata['routing']['approval_required']}")
        print("-" * 60)
    
    print("\nDomain Classifier test complete!")
