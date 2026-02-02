#!/usr/bin/env python3
"""
Email Service for Write It Great Proposal Evaluations
Uses Mailchimp for transactional emails.
"""

import os
import requests
import base64
from datetime import datetime

# Mailchimp configuration
MAILCHIMP_API_KEY = os.getenv('MAILCHIMP_API_KEY')
MAILCHIMP_SERVER = os.getenv('MAILCHIMP_SERVER', 'us1')  # e.g., us1, us21
MAILCHIMP_FROM_EMAIL = os.getenv('MAILCHIMP_FROM_EMAIL', 'proposals@writeitgreat.com')
MAILCHIMP_FROM_NAME = os.getenv('MAILCHIMP_FROM_NAME', 'Write It Great')

# Team notification email
TEAM_EMAIL = os.getenv('TEAM_EMAIL', 'team@writeitgreat.com')


def get_tier_emoji(tier):
    """Get emoji for tier."""
    return {'A': '🌟', 'B': '⭐', 'C': '📋', 'D': '📁'}.get(tier, '📄')


def get_tier_action(tier):
    """Get required action for tier."""
    actions = {
        'A': 'PRIORITY: Review and schedule strategy call within 24 hours',
        'B': 'Review and schedule discovery call within 48 hours',
        'C': 'Auto-processed - Feedback sent with coaching information',
        'D': 'Auto-processed - Decline sent with feedback and resources'
    }
    return actions.get(tier, 'Review required')


def send_team_notification(evaluation, report_path=None):
    """
    Send notification email to the Write It Great team.
    
    Args:
        evaluation: dict containing evaluation results
        report_path: optional path to PDF report to attach
    """
    if not MAILCHIMP_API_KEY:
        print("Mailchimp not configured - skipping team notification")
        _send_fallback_notification(evaluation)
        return False
    
    tier = evaluation.get('tier', 'C')
    emoji = get_tier_emoji(tier)
    action = get_tier_action(tier)
    
    subject = f"{emoji} [{tier}-Tier] New Proposal: {evaluation.get('book_title', 'Unknown')} by {evaluation.get('author_name', 'Unknown')}"
    
    # Build HTML email body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #1a1a1a; }}
            .header {{ background: #1a1a1a; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .tier-badge {{ 
                display: inline-block; 
                padding: 10px 20px; 
                font-size: 24px; 
                font-weight: bold; 
                border-radius: 5px;
                color: white;
                background: {'#2e7d32' if tier == 'A' else '#1976d2' if tier == 'B' else '#f57c00' if tier == 'C' else '#d32f2f'};
            }}
            .score {{ font-size: 36px; font-weight: bold; color: #c9a962; }}
            .action-box {{ 
                background: {'#e8f5e9' if tier in ['A', 'B'] else '#fff3e0'}; 
                border-left: 4px solid {'#2e7d32' if tier == 'A' else '#1976d2' if tier == 'B' else '#f57c00'};
                padding: 15px; 
                margin: 20px 0; 
            }}
            .info-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .info-table td {{ padding: 8px; border-bottom: 1px solid #eee; }}
            .info-table td:first-child {{ font-weight: bold; width: 150px; }}
            .scores-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .scores-table th, .scores-table td {{ padding: 10px; text-align: left; border: 1px solid #ddd; }}
            .scores-table th {{ background: #1a1a1a; color: white; }}
            .footer {{ background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Write It Great</h1>
            <p>New Book Proposal Submission</p>
        </div>
        
        <div class="content">
            <div style="text-align: center; margin: 20px 0;">
                <span class="tier-badge">TIER {tier}</span>
                <span class="score">{evaluation.get('total_score', 0)}/100</span>
            </div>
            
            <div class="action-box">
                <strong>⚡ Action Required:</strong> {action}
            </div>
            
            <h2>Submission Details</h2>
            <table class="info-table">
                <tr><td>Submission ID</td><td>{evaluation.get('submission_id', 'N/A')}</td></tr>
                <tr><td>Book Title</td><td>{evaluation.get('book_title', 'N/A')}</td></tr>
                <tr><td>Author</td><td>{evaluation.get('author_name', 'N/A')}</td></tr>
                <tr><td>Email</td><td><a href="mailto:{evaluation.get('author_email', '')}">{evaluation.get('author_email', 'N/A')}</a></td></tr>
                <tr><td>Proposal Type</td><td>{evaluation.get('proposal_type', 'full').replace('_', ' ').title()}</td></tr>
                <tr><td>Submitted</td><td>{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td></tr>
            </table>
            
            <h2>Executive Summary</h2>
            <p>{evaluation.get('executive_summary', 'No summary available.')}</p>
            
            <h2>Score Breakdown</h2>
            <table class="scores-table">
                <tr>
                    <th>Category</th>
                    <th>Score</th>
                </tr>
                <tr><td>Marketing & Platform</td><td>{evaluation.get('scores', {}).get('marketing', 0)}/100</td></tr>
                <tr><td>Overview & Concept</td><td>{evaluation.get('scores', {}).get('overview', 0)}/100</td></tr>
                <tr><td>Author Credentials</td><td>{evaluation.get('scores', {}).get('credentials', 0)}/100</td></tr>
                <tr><td>Comparative Titles</td><td>{evaluation.get('scores', {}).get('comps', 0)}/100</td></tr>
                <tr><td>Sample Writing</td><td>{evaluation.get('scores', {}).get('writing', 0)}/100</td></tr>
                <tr><td>Book Outline</td><td>{evaluation.get('scores', {}).get('outline', 0)}/100</td></tr>
                <tr><td>Completeness</td><td>{evaluation.get('scores', {}).get('completeness', 0)}/100</td></tr>
            </table>
            
            <h2>Top Strengths</h2>
            <ul>
                {''.join(f'<li>{s}</li>' for s in evaluation.get('top_3_strengths', ['No strengths identified']))}
            </ul>
            
            <h2>Key Improvements Needed</h2>
            <ul>
                {''.join(f'<li>{i}</li>' for i in evaluation.get('top_3_improvements', ['No improvements identified']))}
            </ul>
            
            <h2>Recommended Next Steps</h2>
            <ol>
                {''.join(f'<li>{s}</li>' for s in evaluation.get('recommended_next_steps', ['Review the full feedback report']))}
            </ol>
            
            <p style="margin-top: 30px;">
                <strong>Note:</strong> The full PDF feedback report is attached to this email.
            </p>
        </div>
        
        <div class="footer">
            <p>© {datetime.now().year} Write It Great LLC. All rights reserved.</p>
            <p>This is an internal notification. Do not forward outside the organization.</p>
        </div>
    </body>
    </html>
    """
    
    # Plain text version
    text_body = f"""
WRITE IT GREAT - NEW PROPOSAL SUBMISSION
========================================

TIER {tier} | Score: {evaluation.get('total_score', 0)}/100

ACTION REQUIRED: {action}

SUBMISSION DETAILS
------------------
Submission ID: {evaluation.get('submission_id', 'N/A')}
Book Title: {evaluation.get('book_title', 'N/A')}
Author: {evaluation.get('author_name', 'N/A')}
Email: {evaluation.get('author_email', 'N/A')}
Proposal Type: {evaluation.get('proposal_type', 'full').replace('_', ' ').title()}
Submitted: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

EXECUTIVE SUMMARY
-----------------
{evaluation.get('executive_summary', 'No summary available.')}

TOP STRENGTHS
-------------
{chr(10).join(f'• {s}' for s in evaluation.get('top_3_strengths', ['No strengths identified']))}

KEY IMPROVEMENTS NEEDED
-----------------------
{chr(10).join(f'• {i}' for i in evaluation.get('top_3_improvements', ['No improvements identified']))}

---
© {datetime.now().year} Write It Great LLC. Internal use only.
"""
    
    # Prepare attachment if report exists
    attachments = []
    if report_path and os.path.exists(report_path):
        with open(report_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
            attachments.append({
                'type': 'application/pdf',
                'name': f"Proposal_Feedback_{evaluation.get('submission_id', 'report')}.pdf",
                'content': content
            })
    
    # Send via Mailchimp Transactional (Mandrill) API
    try:
        # For Mailchimp Transactional/Mandrill
        url = f"https://mandrillapp.com/api/1.0/messages/send.json"
        
        payload = {
            "key": MAILCHIMP_API_KEY,
            "message": {
                "html": html_body,
                "text": text_body,
                "subject": subject,
                "from_email": MAILCHIMP_FROM_EMAIL,
                "from_name": MAILCHIMP_FROM_NAME,
                "to": [
                    {"email": TEAM_EMAIL, "name": "Write It Great Team", "type": "to"}
                ],
                "attachments": attachments,
                "tags": ["proposal-evaluation", f"tier-{tier.lower()}"],
            }
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ Team notification sent successfully to {TEAM_EMAIL}")
            return True
        else:
            print(f"❌ Failed to send email: {response.status_code} - {response.text}")
            _send_fallback_notification(evaluation)
            return False
            
    except Exception as e:
        print(f"❌ Email error: {e}")
        _send_fallback_notification(evaluation)
        return False


def send_author_notification(evaluation, report_url):
    """
    Send notification email to the author.
    Note: Currently authors download directly from the results page.
    This function can be used for follow-up emails.
    """
    # Implementation for author emails if needed
    pass


def _send_fallback_notification(evaluation):
    """Print notification to console as fallback when email fails."""
    tier = evaluation.get('tier', 'C')
    print("\n" + "="*60)
    print(f"📧 TEAM NOTIFICATION (Email not configured)")
    print("="*60)
    print(f"Tier: {tier} | Score: {evaluation.get('total_score', 0)}/100")
    print(f"Book: {evaluation.get('book_title', 'N/A')}")
    print(f"Author: {evaluation.get('author_name', 'N/A')} ({evaluation.get('author_email', 'N/A')})")
    print(f"Type: {evaluation.get('proposal_type', 'full')}")
    print(f"ID: {evaluation.get('submission_id', 'N/A')}")
    print("-"*60)
    print(f"Summary: {evaluation.get('executive_summary', 'N/A')[:200]}...")
    print("="*60 + "\n")
