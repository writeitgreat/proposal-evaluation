#!/usr/bin/env python3
"""
Email service for sending reports and notifications.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


def send_report_to_author(proposal, pdf_path):
    """
    Send the evaluation report to the author via email.
    
    Args:
        proposal: Proposal object with author_email, author_name, book_title, tier
        pdf_path: Path to the PDF report file
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('FROM_EMAIL', 'hello@writeitgreat.com')
    
    if not smtp_user or not smtp_password:
        print("Email not configured - skipping author notification")
        return False
    
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = proposal.author_email
    msg['Subject'] = f"Your Book Proposal Evaluation - {proposal.book_title}"
    
    # Email body based on tier
    if proposal.tier in ['A', 'B']:
        tier_message = """
We're excited to share that your proposal shows strong potential! Based on our evaluation, 
we believe your book has what it takes to capture publisher interest.

Our team will be reaching out shortly to discuss next steps and how we can help you 
move forward in your publishing journey.
"""
    else:
        tier_message = """
Thank you for submitting your proposal. We've completed our evaluation and have 
attached a detailed report with our findings.

The report includes specific action items and areas for improvement that could 
strengthen your proposal. We encourage you to review our feedback carefully.
"""
    
    body = f"""Dear {proposal.author_name},

Thank you for submitting your book proposal "{proposal.book_title}" to Write It Great LLC.

{tier_message}

Please find your detailed evaluation report attached to this email.

If you have any questions about the evaluation, feel free to reply to this email.

Best regards,
The Write It Great Team

---
Write It Great LLC
www.writeitgreat.com
"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach PDF
    try:
        with open(pdf_path, 'rb') as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
            safe_title = proposal.book_title.replace(' ', '_').replace('/', '-')[:50]
            pdf_attachment.add_header('Content-Disposition', 'attachment', 
                                      filename=f"Evaluation_Report_{safe_title}.pdf")
            msg.attach(pdf_attachment)
    except Exception as e:
        print(f"Error attaching PDF: {e}")
        return False
    
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, proposal.author_email, msg.as_string())
        server.quit()
        print(f"Report sent to {proposal.author_email}")
        return True
    except Exception as e:
        print(f"Error sending email to author: {e}")
        return False


def send_team_notification(proposal):
    """
    Send notification to team about new proposal.
    
    Args:
        proposal: Proposal object with all fields
    """
    team_emails = os.getenv('TEAM_EMAILS', '').split(',')
    team_emails = [e.strip() for e in team_emails if e.strip()]
    
    if not team_emails:
        print("No team emails configured")
        return
    
    smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_email = os.getenv('FROM_EMAIL', 'hello@writeitgreat.com')
    
    if not smtp_user or not smtp_password:
        print("Email not configured - skipping team notification")
        return
    
    tier_emoji = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🔴'}.get(proposal.tier, '⚪')
    
    subject = f"{tier_emoji} New {proposal.tier}-Tier Proposal: {proposal.book_title}"
    
    app_url = os.getenv('APP_URL', 'https://your-app.herokuapp.com')
    
    body = f"""New Book Proposal Submitted

Author: {proposal.author_name}
Email: {proposal.author_email}
Title: {proposal.book_title}

Tier: {proposal.tier} ({proposal.total_score:.0f}/100)
Type: {proposal.proposal_type}

Submitted: {proposal.submitted_at.strftime('%Y-%m-%d %H:%M UTC')}

View in admin dashboard: {app_url}/admin/proposal/{proposal.id}
"""
    
    for email in team_emails:
        try:
            msg = MIMEText(body)
            msg['From'] = from_email
            msg['To'] = email
            msg['Subject'] = subject
            
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, email, msg.as_string())
            server.quit()
            print(f"Team notification sent to {email}")
        except Exception as e:
            print(f"Error sending team notification to {email}: {e}")
