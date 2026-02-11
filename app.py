#!/usr/bin/env python3
"""
Write It Great - Book Proposal Evaluation System
Flask application with database, admin dashboard, status tracking, and email notifications
"""

import os
import json
import uuid
import smtplib
import traceback
import threading
from io import BytesIO
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
import openai
from docx import Document
import PyPDF2

# ============================================================================
# FLASK APP CONFIGURATION
# ============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///proposals.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'
login_manager.login_message = None  # Disable "Please log in" message

# OpenAI client
client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# Email configuration
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', '') or SMTP_USER
TEAM_EMAILS = (os.environ.get('TEAM_EMAIL') or os.environ.get('TEAM_EMAILS') or 'anna@writeitgreat.com').split(',')

# Status options for proposals
STATUS_OPTIONS = [
    ('submitted', 'Submitted'),
    ('read', 'Read'),
    ('author_call_scheduled', 'Author Call Scheduled'),
    ('author_call_completed', 'Author Call Completed'),
    ('contract_sent', 'Contract Sent'),
    ('contract_signed', 'Contract Signed'),
    ('shopping', 'Shopping with Publishers'),
    ('publisher_interest', 'Publisher Interest'),
    ('offer_received', 'Offer Received'),
    ('deal_closed', 'Deal Closed'),
    ('declined', 'Declined'),
    ('on_hold', 'On Hold'),
]

# ============================================================================
# DATABASE MODELS
# ============================================================================

class AdminUser(UserMixin, db.Model):
    """Admin user model for secure dashboard access"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    password_reset_token = db.Column(db.String(100))
    password_reset_expires = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_reset_token(self):
        self.password_reset_token = uuid.uuid4().hex
        self.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        return self.password_reset_token

    def verify_reset_token(self, token):
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        if self.password_reset_token != token:
            return False
        if datetime.utcnow() > self.password_reset_expires:
            return False
        return True


class Proposal(db.Model):
    """Book proposal submission model"""
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.String(50), unique=True, nullable=False)
    
    # Author info
    author_name = db.Column(db.String(200), nullable=False)
    author_email = db.Column(db.String(200), nullable=False)
    book_title = db.Column(db.String(500), nullable=False)
    
    # Submission details
    proposal_type = db.Column(db.String(50), default='full')
    ownership_confirmed = db.Column(db.Boolean, default=True)
    
    # Evaluation results
    tier = db.Column(db.String(10))
    overall_score = db.Column(db.Float)
    evaluation_json = db.Column(db.Text)
    proposal_text = db.Column(db.Text)

    # Original uploaded file
    original_filename = db.Column(db.String(500))
    original_file = db.Column(db.LargeBinary)
    
    # Status tracking
    status = db.Column(db.String(50), default='submitted')
    notes = db.Column(db.Text)
    
    # Timestamps
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Email tracking
    author_email_sent = db.Column(db.Boolean, default=False)
    team_email_sent = db.Column(db.Boolean, default=False)


@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_submission_id():
    """Generate unique submission ID"""
    date_str = datetime.now().strftime('%Y%m%d')
    random_str = uuid.uuid4().hex[:5].upper()
    return f"WIG-{date_str}-{random_str}"


def extract_text_from_pdf(file):
    """Extract text from PDF file"""
    try:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""


def extract_text_from_docx(file):
    """Extract text from DOCX file"""
    try:
        doc = Document(file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return ""


# Scoring weights for full proposals
FULL_WEIGHTS = {
    'marketing': 0.30,
    'overview': 0.20,
    'credentials': 0.15,
    'comps': 0.10,
    'writing': 0.15,
    'outline': 0.05,
    'completeness': 0.05
}

MARKETING_ONLY_WEIGHTS = {
    'marketing': 1.00, 'overview': 0.00, 'credentials': 0.00,
    'comps': 0.00, 'writing': 0.00, 'outline': 0.00, 'completeness': 0.00
}

NO_MARKETING_WEIGHTS = {
    'marketing': 0.00, 'overview': 0.29, 'credentials': 0.21,
    'comps': 0.14, 'writing': 0.21, 'outline': 0.07, 'completeness': 0.08
}


def get_weights_for_type(proposal_type):
    if proposal_type == 'marketing_only':
        return MARKETING_ONLY_WEIGHTS
    elif proposal_type == 'no_marketing':
        return NO_MARKETING_WEIGHTS
    return FULL_WEIGHTS


def calculate_weighted_score(scores, proposal_type):
    weights = get_weights_for_type(proposal_type)
    total = 0
    for category, weight in weights.items():
        score_data = scores.get(category, 0)
        score = score_data.get('score', 0) if isinstance(score_data, dict) else score_data
        total += float(score or 0) * weight
    return round(total, 2)


def determine_tier(score):
    if score >= 85:
        return 'A'
    elif score >= 70:
        return 'B'
    elif score >= 60:
        return 'C'
    return 'D'


def get_tier_description(tier):
    return {
        'A': 'Exceptional - Your proposal demonstrates strong potential for top-tier publishers.',
        'B': 'Strong Foundation - With targeted improvements, your proposal could reach A-tier status.',
        'C': 'Developing - Your proposal shows promise but needs significant strengthening in key areas.',
        'D': 'Early Stage - Your proposal needs substantial work before submission to publishers.'
    }.get(tier, '')


def evaluate_proposal(proposal_text, proposal_type='full', author_name='', book_title=''):
    """Evaluate proposal using OpenAI with comprehensive analysis"""

    if proposal_type == 'marketing_only':
        evaluation_focus = "You are evaluating ONLY the Marketing & Platform section. Score all other categories as 0."
    elif proposal_type == 'no_marketing':
        evaluation_focus = "This proposal does NOT include a Marketing section. Score Marketing as 0. Evaluate all other sections normally."
    else:
        evaluation_focus = "This is a FULL proposal submission. Evaluate all categories comprehensively."

    system_prompt = """You are an elite literary agent with 25+ years of experience evaluating book proposals for major publishers. You have placed hundreds of books with advances ranging from $50,000 to $2 million+. Your evaluations are known for being thorough, actionable, and honest.

Your evaluation style:
- Be specific and cite examples from the actual proposal text
- Provide actionable feedback that authors can implement immediately
- Be encouraging but honest about weaknesses
- Think like a publisher evaluating commercial viability"""

    user_prompt = f"""{evaluation_focus}

Evaluate this book proposal comprehensively.

AUTHOR: {author_name}
BOOK TITLE: {book_title}

PROPOSAL TEXT:
{proposal_text[:50000]}

---

Provide your evaluation as a JSON object with this EXACT structure:

{{
    "executiveSummary": "<3-5 sentence executive summary of strengths and areas for improvement>",

    "redFlags": ["<list critical issues like: no_platform, weak_credentials, oversaturated_market, poor_writing_quality, incomplete_proposal, unrealistic_claims, no_clear_audience, derivative_concept>"],

    "scores": {{
        "marketing": {{"score": <0-100>, "weight": 30}},
        "overview": {{"score": <0-100>, "weight": 20}},
        "credentials": {{"score": <0-100>, "weight": 15}},
        "comps": {{"score": <0-100>, "weight": 10}},
        "writing": {{"score": <0-100>, "weight": 15}},
        "outline": {{"score": <0-100>, "weight": 5}},
        "completeness": {{"score": <0-100>, "weight": 5}}
    }},

    "detailedAnalysis": {{
        "marketing": {{
            "currentState": "<2-3 sentences describing current state>",
            "strengths": "<what's working well>",
            "gaps": "<what's missing or weak>",
            "exampleOfExcellence": "<specific example of what A-tier looks like for this category>",
            "actionItems": ["<specific action 1>", "<specific action 2>", "<specific action 3>"]
        }},
        "overview": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"]
        }},
        "credentials": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"]
        }},
        "comps": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"]
        }},
        "writing": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"],
            "writingExamples": {{
                "strongPassage": "<quote a strong passage from the proposal if available>",
                "improvementExample": "<quote a passage that could be improved>"
            }}
        }},
        "outline": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"]
        }},
        "completeness": {{
            "currentState": "<2-3 sentences>",
            "strengths": "<what's working>",
            "gaps": "<what's missing>",
            "exampleOfExcellence": "<A-tier example>",
            "actionItems": ["<action 1>", "<action 2>", "<action 3>"]
        }}
    }},

    "strengths": ["<top strength 1>", "<top strength 2>", "<top strength 3>"],
    "improvements": ["<top improvement 1>", "<top improvement 2>", "<top improvement 3>"],

    "priorityActionPlan": [
        {{"priority": 1, "action": "<most important action>", "timeline": "<e.g., This week>", "impact": "<why this matters>"}},
        {{"priority": 2, "action": "<second action>", "timeline": "<e.g., Next 2 weeks>", "impact": "<why this matters>"}},
        {{"priority": 3, "action": "<third action>", "timeline": "<e.g., Next month>", "impact": "<why this matters>"}}
    ],

    "pathToATier": "<2-3 sentences describing the specific path this author needs to take to reach A-tier status>",

    "advanceEstimate": {{
        "viable": <true or false>,
        "lowRange": <number or 0>,
        "highRange": <number or 0>,
        "confidence": "<Low, Medium, or High>",
        "reasoning": "<2-3 sentences explaining the estimate>"
    }},

    "recommendedNextSteps": ["<step 1>", "<step 2>", "<step 3>", "<step 4>", "<step 5>"]
}}

SCORING GUIDELINES:
- A-Tier (85-100): Exceptional, publisher-ready proposal with strong platform
- B-Tier (70-84): Strong foundation, improvements needed to be publisher-ready
- C-Tier (60-69): Developing, shows promise but needs significant strengthening
- D-Tier (Below 60): Early stage, needs substantial work before submission

IMPORTANT: Your scores MUST align with the tier. If a proposal deserves a B, score it 70-84. If it deserves a C, score it 60-69. Do NOT give a score of 72 and call it C-tier - that would be B-tier.

ADVANCE ESTIMATE RULES (STRICT - you MUST follow these exactly):
- A-Tier (score >= 85): viable=true, lowRange 0-25000, highRange max 25000
- B-Tier (score 70-84): viable=true, lowRange 0-10000, highRange max 10000
- C-Tier (score 60-69): viable=false, lowRange=0, highRange=0
- D-Tier (score < 60): viable=false, lowRange=0, highRange=0
- NEVER estimate an advance higher than $25,000
- For C and D tier proposals, ALWAYS set viable=false and both ranges to 0

Return ONLY the JSON object, no other text."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0,
            seed=42,
            max_tokens=6000
        )

        response_text = response.choices[0].message.content.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        evaluation = json.loads(response_text.strip())

        # Calculate weighted total score
        scores = evaluation.get('scores', {})
        evaluation['total_score'] = calculate_weighted_score(scores, proposal_type)
        evaluation['tier'] = determine_tier(evaluation['total_score'])
        evaluation['tierDescription'] = get_tier_description(evaluation['tier'])
        evaluation['proposal_type'] = proposal_type

        # Enforce advance estimate caps based on tier (strict business rules)
        tier = evaluation['tier']
        adv = evaluation.get('advanceEstimate', {})
        if tier in ('C', 'D'):
            adv['viable'] = False
            adv['lowRange'] = 0
            adv['highRange'] = 0
            if not adv.get('reasoning'):
                adv['reasoning'] = 'Proposal needs significant development before it could attract a traditional publishing advance.'
        elif tier == 'B':
            adv['viable'] = True
            adv['lowRange'] = min(int(adv.get('lowRange', 0) or 0), 10000)
            adv['highRange'] = min(int(adv.get('highRange', 0) or 0), 10000)
        elif tier == 'A':
            adv['viable'] = True
            adv['lowRange'] = min(int(adv.get('lowRange', 0) or 0), 25000)
            adv['highRange'] = min(int(adv.get('highRange', 0) or 0), 25000)
        evaluation['advanceEstimate'] = adv

        # Backward-compat aliases so old templates/emails still work
        evaluation['overall_score'] = evaluation['total_score']
        evaluation['summary'] = evaluation.get('executiveSummary', '')
        evaluation['red_flags'] = evaluation.get('redFlags', [])
        evaluation['next_steps'] = evaluation.get('recommendedNextSteps', [])
        evaluation['advance_estimate'] = {
            'low': adv.get('lowRange', 0),
            'high': adv.get('highRange', 0),
            'notes': adv.get('reasoning', '')
        }
        # Map scores to old categories format for backward compat
        cats = {}
        for key, score_data in scores.items():
            s = score_data.get('score', 0) if isinstance(score_data, dict) else score_data
            da = evaluation.get('detailedAnalysis', {}).get(key, {})
            cats[key] = {
                'score': s,
                'feedback': da.get('currentState', ''),
                'priority_actions': da.get('actionItems', [])
            }
        evaluation['categories'] = cats

        return evaluation
    except Exception as e:
        print(f"Evaluation error: {e}")
        traceback.print_exc()
        return None


def generate_pdf_report(proposal):
    """Generate PDF report for proposal using xhtml2pdf"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}

    # Ensure numeric values are properly typed
    advance = evaluation.get('advance_estimate')
    if advance and isinstance(advance, dict):
        try:
            advance['low'] = float(advance.get('low', 0) or 0)
            advance['high'] = float(advance.get('high', 0) or 0)
        except (ValueError, TypeError):
            advance['low'] = 0
            advance['high'] = 0

    adv_est = evaluation.get('advanceEstimate')
    if adv_est and isinstance(adv_est, dict):
        try:
            adv_est['lowRange'] = float(adv_est.get('lowRange', 0) or 0)
            adv_est['highRange'] = float(adv_est.get('highRange', 0) or 0)
        except (ValueError, TypeError):
            adv_est['lowRange'] = 0
            adv_est['highRange'] = 0

    scores = evaluation.get('scores', {})
    for key, score_data in scores.items():
        if isinstance(score_data, dict):
            try:
                score_data['score'] = float(score_data.get('score', 0) or 0)
            except (ValueError, TypeError):
                score_data['score'] = 0

    categories = evaluation.get('categories', {})
    for key, cat in categories.items():
        if isinstance(cat, dict):
            try:
                cat['score'] = float(cat.get('score', 0) or 0)
            except (ValueError, TypeError):
                cat['score'] = 0

    html = render_template('report_pdf.html', proposal=proposal, evaluation=evaluation)
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)
    if pisa_status.err:
        print(f"PDF generation error: {pisa_status.err}")
        raise Exception(f"PDF generation failed with {pisa_status.err} errors")
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


def send_email(to_email, subject, html_content, attachments=None):
    """Send email via SMTP"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Email not configured - skipping")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(html_content, 'html'))
        
        if attachments:
            for filename, content in attachments:
                attachment = MIMEApplication(content)
                attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(attachment)
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"Email SMTP auth error: {e}")
        print("HINT: Gmail requires an App Password (16-char) when 2FA is enabled.")
        print("Generate one at: https://myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_author_notification(proposal):
    """Send evaluation results to the author"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}

    score_display = f"{proposal.overall_score:.0f}" if proposal.overall_score is not None else "N/A"
    summary = evaluation.get('executiveSummary', '') or evaluation.get('summary', 'See attached report for details.')
    tier_desc = evaluation.get('tierDescription', '')
    app_url = os.environ.get('APP_URL', 'http://localhost:5000')

    subject = f"Your Book Proposal Evaluation - {proposal.book_title}"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <h1 style="color: #2D1B69; margin-bottom: 5px;">Write It Great</h1>
                <p style="color: #666; font-style: italic;">Elite Ghostwriting &amp; Publishing Services</p>
            </div>

            <p>Dear {proposal.author_name},</p>

            <p>Thank you for submitting your book proposal for <strong>"{proposal.book_title}"</strong> to Write It Great. Our AI-powered evaluation system has completed a comprehensive analysis of your proposal.</p>

            <div style="background: #f8f6f9; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center;">
                <div style="font-size: 48px; font-weight: bold; color: {'#2e7d32' if proposal.tier == 'A' else '#1976d2' if proposal.tier == 'B' else '#f57c00' if proposal.tier == 'C' else '#d32f2f'};">{proposal.tier or 'N/A'}-Tier</div>
                <div style="font-size: 24px; color: #2D1B69; margin: 10px 0;">{score_display}/100</div>
                <div style="color: #666; font-style: italic;">{tier_desc}</div>
            </div>

            <h3 style="color: #2D1B69;">Executive Summary</h3>
            <p>{summary}</p>

            <div style="text-align: center; margin: 25px 0;">
                <a href="{app_url}/results/{proposal.submission_id}" style="display: inline-block; padding: 14px 28px; background: #B8F2B8; color: #1a3a1a; text-decoration: none; border-radius: 8px; font-weight: bold;">View Your Full Report</a>
            </div>

            <p>Your complete evaluation report is also attached as a PDF for your records.</p>

            <p>A member of our team will reach out within 3-5 business days to discuss your results and next steps.</p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">

            <p>Best regards,<br><strong>The Write It Great Team</strong><br><a href="https://www.writeitgreat.com" style="color: #2D1B69;">www.writeitgreat.com</a></p>
        </div>
    </body>
    </html>
    """

    # Try to generate PDF attachment, but send email even if PDF fails
    attachments = None
    try:
        pdf_content = generate_pdf_report(proposal)
        attachments = [(f"Book_Proposal_Evaluation_{proposal.submission_id}.pdf", pdf_content)]
    except Exception as e:
        print(f"PDF generation for author email failed (sending without attachment): {e}")

    try:
        return send_email(proposal.author_email, subject, html_content, attachments)
    except Exception as e:
        print(f"Author notification error: {e}")
        return False


def send_team_notification(proposal):
    """Send notification to team about new submission"""
    try:
        evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}

        score_display = f"{proposal.overall_score:.0f}" if proposal.overall_score is not None else "N/A"
        summary = evaluation.get('executiveSummary', '') or evaluation.get('summary', 'No summary')

        subject = f"[{proposal.tier or 'N/A'}-Tier] New Proposal: {proposal.book_title}"

        # Build score breakdown
        scores = evaluation.get('scores', {})
        score_rows = ""
        category_labels = {
            'marketing': 'Marketing & Platform', 'overview': 'Overview & Concept',
            'credentials': 'Author Credentials', 'comps': 'Comparative Titles',
            'writing': 'Sample Writing', 'outline': 'Book Outline', 'completeness': 'Completeness'
        }
        for key, label in category_labels.items():
            score_data = scores.get(key, {})
            s = score_data.get('score', 0) if isinstance(score_data, dict) else score_data
            score_rows += f"<tr><td>{label}</td><td style='text-align:center;font-weight:bold;'>{int(float(s or 0))}/100</td></tr>"

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <div style="background: #2D1B69; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0;">Write It Great</h1>
                <p style="margin: 5px 0 0;">New Book Proposal Submission</p>
            </div>
            <div style="padding: 20px;">
                <div style="text-align: center; margin: 20px 0;">
                    <span style="display: inline-block; padding: 10px 20px; font-size: 24px; font-weight: bold; border-radius: 5px; color: white; background: {'#2e7d32' if proposal.tier == 'A' else '#1976d2' if proposal.tier == 'B' else '#f57c00' if proposal.tier == 'C' else '#d32f2f'};">
                        TIER {proposal.tier or 'N/A'}
                    </span>
                    <span style="font-size: 36px; font-weight: bold; color: #2D1B69; margin-left: 20px;">{score_display}/100</span>
                </div>

                <h2>Submission Details</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold; width: 150px;">Author</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{proposal.author_name}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Email</td><td style="padding: 8px; border-bottom: 1px solid #eee;"><a href="mailto:{proposal.author_email}">{proposal.author_email}</a></td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Book Title</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{proposal.book_title}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">Submission ID</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{proposal.submission_id}</td></tr>
                </table>

                <h2>Executive Summary</h2>
                <p>{summary}</p>

                {'<h2>Score Breakdown</h2><table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;"><tr style="background: #2D1B69; color: white;"><th style="padding: 10px; text-align: left;">Category</th><th style="padding: 10px; text-align: center;">Score</th></tr>' + score_rows + '</table>' if score_rows else ''}

                <div style="margin-top: 20px;">
                    <a href="{os.environ.get('APP_URL', 'http://localhost:5000')}/admin/proposal/{proposal.submission_id}" style="display: inline-block; padding: 12px 24px; background: #B8F2B8; color: #1a3a1a; text-decoration: none; border-radius: 5px; font-weight: bold;">View Evaluation</a>
                    <a href="{os.environ.get('APP_URL', 'http://localhost:5000')}/admin/proposal/{proposal.submission_id}/view-proposal" style="display: inline-block; padding: 12px 24px; background: #2D1B69; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; margin-left: 10px;">Read Proposal Text</a>
                    <a href="{os.environ.get('APP_URL', 'http://localhost:5000')}/admin/proposal/{proposal.submission_id}/download-proposal" style="display: inline-block; padding: 12px 24px; background: white; color: #2D1B69; text-decoration: none; border-radius: 5px; font-weight: bold; margin-left: 10px; border: 2px solid #2D1B69;">Download Original File</a>
                </div>
            </div>
        </body>
        </html>
        """

        success = True
        for email in TEAM_EMAILS:
            if email.strip():
                if not send_email(email.strip(), subject, html_content):
                    success = False

        return success
    except Exception as e:
        print(f"Team notification error: {e}")
        traceback.print_exc()
        return False


# ============================================================================
# BACKGROUND PROCESSING
# ============================================================================

def process_evaluation_background(app_obj, submission_id, proposal_text, proposal_type, author_name='', book_title=''):
    """Run OpenAI evaluation and email notifications in a background thread"""
    with app_obj.app_context():
        try:
            proposal = Proposal.query.filter_by(submission_id=submission_id).first()
            if not proposal:
                print(f"Background eval: proposal {submission_id} not found")
                return

            evaluation = evaluate_proposal(proposal_text, proposal_type, author_name, book_title)
            if not evaluation:
                proposal.status = 'error'
                db.session.commit()
                print(f"Background eval: OpenAI evaluation failed for {submission_id}")
                return

            proposal.tier = evaluation.get('tier', 'C')
            proposal.overall_score = evaluation.get('total_score', evaluation.get('overall_score', 50))
            proposal.evaluation_json = json.dumps(evaluation)
            proposal.status = 'submitted'
            db.session.commit()

            # Send emails
            try:
                if send_author_notification(proposal):
                    proposal.author_email_sent = True
                if send_team_notification(proposal):
                    proposal.team_email_sent = True
                db.session.commit()
            except Exception as email_error:
                print(f"Email error (non-fatal): {email_error}")

            print(f"Background eval: completed for {submission_id}")

        except Exception as e:
            print(f"Background eval error for {submission_id}: {e}")
            traceback.print_exc()
            try:
                proposal = Proposal.query.filter_by(submission_id=submission_id).first()
                if proposal:
                    proposal.status = 'error'
                    db.session.commit()
            except Exception:
                pass


# ============================================================================
# PUBLIC ROUTES
# ============================================================================

@app.route('/')
def index():
    """Main submission form"""
    return render_template('index.html')


@app.route('/api/evaluate', methods=['POST'])
def api_evaluate():
    """Handle proposal submission and evaluation"""
    try:
        author_name = request.form.get('author_name', '').strip()
        author_email = request.form.get('author_email', '').strip()
        book_title = request.form.get('book_title', '').strip()
        proposal_type = request.form.get('proposal_type', 'full')

        if not all([author_name, author_email, book_title]):
            return jsonify({'success': False, 'error': 'Please fill in all required fields.'})

        file = request.files.get('proposal_file')
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': 'Please upload your proposal document.'})

        original_filename = secure_filename(file.filename)
        filename = original_filename.lower()
        if filename.endswith('.pdf'):
            # Read file bytes for storage, then reset for text extraction
            file_bytes = file.read()
            file.seek(0)
            proposal_text = extract_text_from_pdf(file)
        elif filename.endswith('.docx') or filename.endswith('.doc'):
            file_bytes = file.read()
            file.seek(0)
            proposal_text = extract_text_from_docx(file)
        else:
            return jsonify({'success': False, 'error': 'Please upload a PDF or Word document.'})

        if len(proposal_text.strip()) < 500:
            return jsonify({'success': False, 'error': 'Could not extract sufficient text from document.'})

        # Save proposal immediately with 'processing' status
        proposal = Proposal(
            submission_id=generate_submission_id(),
            author_name=author_name,
            author_email=author_email,
            book_title=book_title,
            proposal_type=proposal_type,
            ownership_confirmed=True,
            proposal_text=proposal_text[:50000],
            original_filename=original_filename,
            original_file=file_bytes,
            status='processing'
        )

        db.session.add(proposal)
        db.session.commit()

        # Run evaluation in background thread to avoid Heroku 30s timeout
        thread = threading.Thread(
            target=process_evaluation_background,
            args=(app, proposal.submission_id, proposal_text, proposal_type, author_name, book_title)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'proposal_id': proposal.submission_id
        })

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'An unexpected error occurred. Please try again.'})


@app.route('/api/status/<submission_id>')
def check_status(submission_id):
    """Check evaluation status (for polling from results page)"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    return jsonify({
        'status': proposal.status,
        'ready': proposal.status not in ('processing',)
    })


@app.route('/results/<submission_id>')
def results(submission_id):
    """Public results page for authors"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    processing = proposal.status == 'processing'
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    return render_template('results.html', proposal=proposal, evaluation=evaluation, processing=processing)


@app.route('/download/<submission_id>')
def download_pdf(submission_id):
    """Download PDF report"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()

    try:
        pdf_content = generate_pdf_report(proposal)
        pdf_buffer = BytesIO(pdf_content)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Book_Proposal_Evaluation_{proposal.submission_id}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"PDF download error: {e}")
        traceback.print_exc()
        flash('Error generating PDF report. Please try again later.', 'error')
        return redirect(url_for('results', submission_id=submission_id))


# ============================================================================
# ADMIN ROUTES
# ============================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        user = AdminUser.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        
        flash('Invalid email or password', 'error')
    
    return render_template('admin_login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    """Admin logout"""
    logout_user()
    return redirect(url_for('admin_login'))


@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard showing all proposals"""
    page = request.args.get('page', 1, type=int)
    tier_filter = request.args.get('tier', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = Proposal.query
    
    if tier_filter:
        query = query.filter_by(tier=tier_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Proposal.author_name.ilike(search_term),
                Proposal.book_title.ilike(search_term),
                Proposal.author_email.ilike(search_term)
            )
        )
    
    proposals = query.order_by(Proposal.submitted_at.desc()).paginate(page=page, per_page=20)
    
    stats = {
        'total': Proposal.query.count(),
        'a_tier': Proposal.query.filter_by(tier='A').count(),
        'b_tier': Proposal.query.filter_by(tier='B').count(),
        'c_tier': Proposal.query.filter_by(tier='C').count(),
        'd_tier': Proposal.query.filter_by(tier='D').count(),
        'submitted': Proposal.query.filter_by(status='submitted').count(),
        'shopping': Proposal.query.filter_by(status='shopping').count(),
    }
    
    return render_template('admin_dashboard.html', 
                         proposals=proposals, 
                         stats=stats,
                         status_options=STATUS_OPTIONS,
                         current_filters={'tier': tier_filter, 'status': status_filter, 'search': search})


@app.route('/admin/proposal/<submission_id>', methods=['GET', 'POST'])
@login_required
def admin_proposal_detail(submission_id):
    """View and edit individual proposal"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    
    if request.method == 'POST':
        new_status = request.form.get('status')
        if new_status and new_status in [s[0] for s in STATUS_OPTIONS]:
            proposal.status = new_status
        
        notes = request.form.get('notes', '')
        proposal.notes = notes
        
        db.session.commit()
        flash('Proposal updated successfully', 'success')
        return redirect(url_for('admin_proposal_detail', submission_id=submission_id))
    
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    return render_template('admin_proposal.html', 
                         proposal=proposal, 
                         evaluation=evaluation,
                         status_options=STATUS_OPTIONS)


@app.route('/admin/proposal/<submission_id>/view-proposal')
@login_required
def view_proposal_text(submission_id):
    """View the original submitted proposal text"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    return render_template('admin_view_proposal.html', proposal=proposal)


@app.route('/admin/proposal/<submission_id>/download-proposal')
@login_required
def download_proposal_text(submission_id):
    """Download the original uploaded file, or extracted text as .txt fallback"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()

    # Serve original file if available
    if proposal.original_file and proposal.original_filename:
        file_buffer = BytesIO(proposal.original_file)
        fname = proposal.original_filename.lower()
        if fname.endswith('.pdf'):
            mimetype = 'application/pdf'
        elif fname.endswith('.docx'):
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif fname.endswith('.doc'):
            mimetype = 'application/msword'
        else:
            mimetype = 'application/octet-stream'
        return send_file(
            file_buffer,
            as_attachment=True,
            download_name=proposal.original_filename,
            mimetype=mimetype
        )

    # Fallback to extracted text
    if not proposal.proposal_text:
        flash('No proposal text available for this submission.', 'error')
        return redirect(url_for('admin_proposal_detail', submission_id=submission_id))

    text_buffer = BytesIO(proposal.proposal_text.encode('utf-8'))
    filename = f"{proposal.author_name.replace(' ', '_')}_{proposal.submission_id}_proposal.txt"
    return send_file(
        text_buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='text/plain'
    )


@app.route('/admin/proposal/<submission_id>/resend-author-email', methods=['POST'])
@login_required
def resend_author_email(submission_id):
    """Resend evaluation email to author"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    
    if send_author_notification(proposal):
        proposal.author_email_sent = True
        db.session.commit()
        flash('Email sent to author successfully', 'success')
    else:
        flash('Failed to send email. Check email configuration.', 'error')
    
    return redirect(url_for('admin_proposal_detail', submission_id=submission_id))


ALLOWED_EMAIL_DOMAIN = 'writeitgreat.com'


@app.route('/admin/register', methods=['GET', 'POST'])
def admin_register():
    """Team registration - restricted to @writeitgreat.com emails"""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if not all([email, name, password, confirm]):
            flash('All fields are required.', 'error')
        elif not email.endswith(f'@{ALLOWED_EMAIL_DOMAIN}'):
            flash(f'Only @{ALLOWED_EMAIL_DOMAIN} email addresses can register.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        elif AdminUser.query.filter_by(email=email).first():
            flash('An account with this email already exists. Try logging in or resetting your password.', 'error')
        else:
            user = AdminUser(email=email, name=name, password_hash='temp')
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f'Welcome, {name}! Your account has been created.', 'success')
            return redirect(url_for('admin_dashboard'))

    return render_template('admin_register.html')


@app.route('/admin/forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    """Request a password reset email"""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = AdminUser.query.filter_by(email=email).first()

        # Always show success message to prevent email enumeration
        flash('If an account exists with that email, a password reset link has been sent.', 'success')

        if user:
            token = user.generate_reset_token()
            db.session.commit()

            app_url = os.environ.get('APP_URL', 'http://localhost:5000')
            reset_url = f"{app_url}/admin/reset-password/{token}"

            reset_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 500px; margin: 0 auto; padding: 20px;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <h1 style="color: #2D1B69; margin-bottom: 5px;">Write It Great</h1>
                    </div>
                    <p>Hi {user.name},</p>
                    <p>You requested a password reset for your Write It Great dashboard account.</p>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{reset_url}" style="display: inline-block; padding: 14px 28px; background: #B8F2B8; color: #1a3a1a; text-decoration: none; border-radius: 8px; font-weight: bold;">Reset Your Password</a>
                    </div>
                    <p style="font-size: 0.875rem; color: #666;">This link expires in 1 hour. If you didn't request this, you can safely ignore this email.</p>
                    <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
                    <p style="font-size: 0.8rem; color: #999;">Write It Great &middot; <a href="https://www.writeitgreat.com" style="color: #2D1B69;">writeitgreat.com</a></p>
                </div>
            </body>
            </html>
            """
            send_email(user.email, 'Password Reset - Write It Great Dashboard', reset_html)

        return redirect(url_for('admin_forgot_password'))

    return render_template('admin_forgot_password.html')


@app.route('/admin/reset-password/<token>', methods=['GET', 'POST'])
def admin_reset_password(token):
    """Reset password using a valid token"""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    user = AdminUser.query.filter_by(password_reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash('This reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('admin_forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            user.set_password(password)
            user.password_reset_token = None
            user.password_reset_expires = None
            db.session.commit()
            flash('Your password has been reset. Please log in.', 'success')
            return redirect(url_for('admin_login'))

    return render_template('admin_reset_password.html', token=token)


# ============================================================================
# DATABASE MIGRATIONS
# ============================================================================

def run_migrations():
    """Add new columns to existing tables if they don't exist"""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    is_postgres = 'postgresql' in str(db.engine.url)
    blob_type = 'BYTEA' if is_postgres else 'BLOB'

    # Proposal table migrations
    proposal_cols = [col['name'] for col in inspector.get_columns('proposal')]
    with db.engine.begin() as conn:
        if 'original_filename' not in proposal_cols:
            conn.execute(text('ALTER TABLE proposal ADD COLUMN original_filename VARCHAR(500)'))
            print("Migration: added proposal.original_filename")
        if 'original_file' not in proposal_cols:
            conn.execute(text(f'ALTER TABLE proposal ADD COLUMN original_file {blob_type}'))
            print("Migration: added proposal.original_file")

    # AdminUser table migrations
    admin_cols = [col['name'] for col in inspector.get_columns('admin_user')]
    with db.engine.begin() as conn:
        if 'password_reset_token' not in admin_cols:
            conn.execute(text('ALTER TABLE admin_user ADD COLUMN password_reset_token VARCHAR(100)'))
            print("Migration: added admin_user.password_reset_token")
        if 'password_reset_expires' not in admin_cols:
            conn.execute(text('ALTER TABLE admin_user ADD COLUMN password_reset_expires TIMESTAMP'))
            print("Migration: added admin_user.password_reset_expires")


# ============================================================================
# CLI COMMANDS
# ============================================================================

@app.cli.command('init-db')
def init_db():
    """Initialize the database"""
    db.create_all()
    run_migrations()
    print("Database initialized!")


@app.cli.command('create-admin')
def create_admin():
    """Create admin user"""
    import getpass
    
    email = input("Enter admin email [anna@writeitgreat.com]: ").strip() or "anna@writeitgreat.com"
    name = input("Enter admin name [Anna]: ").strip() or "Anna"
    password = getpass.getpass("Enter password: ")
    
    existing = AdminUser.query.filter_by(email=email).first()
    if existing:
        print(f"User {email} already exists. Updating password...")
        existing.set_password(password)
    else:
        user = AdminUser(email=email, name=name)
        user.set_password(password)
        db.session.add(user)
    
    db.session.commit()
    print(f"Admin user '{email}' created/updated successfully!")


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error_code=404, error_message="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error_code=500, error_message="Server error"), 500


with app.app_context():
    db.create_all()
    try:
        run_migrations()
    except Exception as e:
        print(f"Migration note: {e}")


if __name__ == '__main__':
    app.run(debug=True, port=5000)
