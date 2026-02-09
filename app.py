#!/usr/bin/env python3
"""
Write It Great - Book Proposal Evaluation System
Flask application with database, admin dashboard, status tracking, and email notifications
"""

import os
import json
import uuid
import tempfile
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from weasyprint import HTML
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
TEAM_EMAILS = os.environ.get('TEAM_EMAILS', 'anna@writeitgreat.com').split(',')

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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


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


def evaluate_proposal(proposal_text, proposal_type='full'):
    """Evaluate proposal using OpenAI"""
    
    system_prompt = """You are an expert book proposal evaluator for Write It Great, an elite ghostwriting and publishing services firm.

Evaluate the proposal and return a JSON object with this exact structure:
{
    "tier": "A" or "B" or "C" or "D",
    "overall_score": 0-100,
    "summary": "2-3 sentence overall assessment",
    "red_flags": ["list of concerns"],
    "strengths": ["list of strengths"],
    "advance_estimate": {
        "low": 0,
        "high": 0,
        "notes": "explanation"
    },
    "categories": {
        "concept": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]},
        "market": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]},
        "author_platform": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]},
        "writing_sample": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]},
        "marketing_plan": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]},
        "competitive_analysis": {"score": 0-100, "feedback": "detailed feedback", "priority_actions": ["actions"]}
    },
    "next_steps": ["prioritized list of 3-5 most important next steps"]
}

TIER DEFINITIONS:
- A-Tier (80-100): Publisher-ready. Strong concept, established platform.
- B-Tier (60-79): Promising with work needed.
- C-Tier (40-59): Significant development needed.
- D-Tier (0-39): Not ready for traditional publishing.

ADVANCE ESTIMATES (non-fiction):
- A-Tier: $15,000-$30,000
- B-Tier: $0-$10,000
- C-Tier: $0-$5,000
- D-Tier: Self-publishing recommended"""

    type_instructions = ""
    if proposal_type == 'marketing_only':
        type_instructions = "\n\nNOTE: This is MARKETING-ONLY. Focus on marketing plan and author platform."
    elif proposal_type == 'no_marketing':
        type_instructions = "\n\nNOTE: This EXCLUDES marketing materials. Score marketing_plan as 0."

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_prompt + type_instructions},
                {"role": "user", "content": f"Evaluate this book proposal:\n\n{proposal_text[:15000]}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        evaluation = json.loads(response.choices[0].message.content)
        return evaluation
    except Exception as e:
        print(f"Evaluation error: {e}")
        return None


def generate_pdf_report(proposal):
    """Generate PDF report for proposal"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    html = render_template('report_pdf.html', proposal=proposal, evaluation=evaluation)
    pdf = HTML(string=html, base_url=request.host_url).write_pdf()
    return pdf


def send_email(to_email, subject, html_content, attachments=None):
    """Send email via SMTP"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("Email not configured - skipping")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
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
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_author_notification(proposal):
    """Send evaluation results to the author"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    
    subject = f"Your Book Proposal Evaluation - {proposal.book_title}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #4a2c5a;">Your Book Proposal Evaluation Results</h2>
            
            <p>Dear {proposal.author_name},</p>
            
            <p>Thank you for submitting your book proposal for <strong>"{proposal.book_title}"</strong> to Write It Great.</p>
            
            <div style="background: #f8f6f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #4a2c5a;">Evaluation Summary</h3>
                <p><strong>Classification:</strong> {proposal.tier}-Tier</p>
                <p><strong>Overall Score:</strong> {proposal.overall_score:.0f}/100</p>
                <p><strong>Summary:</strong> {evaluation.get('summary', 'See attached report for details.')}</p>
            </div>
            
            <p>Your complete evaluation report is attached as a PDF.</p>
            
            <p>A member of our team will reach out within 3-5 business days.</p>
            
            <p>Best regards,<br><strong>The Write It Great Team</strong></p>
        </div>
    </body>
    </html>
    """
    
    try:
        pdf_content = generate_pdf_report(proposal)
        attachments = [(f"Book_Proposal_Evaluation_{proposal.submission_id}.pdf", pdf_content)]
        return send_email(proposal.author_email, subject, html_content, attachments)
    except Exception as e:
        print(f"Author notification error: {e}")
        return False


def send_team_notification(proposal):
    """Send notification to team about new submission"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    
    subject = f"[{proposal.tier}-Tier] New Proposal: {proposal.book_title}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: #4a2c5a;">New Book Proposal Submission</h2>
        <p><strong>Author:</strong> {proposal.author_name}</p>
        <p><strong>Email:</strong> {proposal.author_email}</p>
        <p><strong>Book Title:</strong> {proposal.book_title}</p>
        <p><strong>Tier:</strong> {proposal.tier}</p>
        <p><strong>Score:</strong> {proposal.overall_score:.0f}/100</p>
        <p><strong>Summary:</strong> {evaluation.get('summary', 'No summary')}</p>
        <p><a href="{os.environ.get('APP_URL', 'http://localhost:5000')}/admin/proposal/{proposal.submission_id}">View Full Proposal</a></p>
    </body>
    </html>
    """
    
    success = True
    for email in TEAM_EMAILS:
        if email.strip():
            if not send_email(email.strip(), subject, html_content):
                success = False
    
    return success


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
        
        filename = secure_filename(file.filename).lower()
        if filename.endswith('.pdf'):
            proposal_text = extract_text_from_pdf(file)
        elif filename.endswith('.docx') or filename.endswith('.doc'):
            proposal_text = extract_text_from_docx(file)
        else:
            return jsonify({'success': False, 'error': 'Please upload a PDF or Word document.'})
        
        if len(proposal_text.strip()) < 500:
            return jsonify({'success': False, 'error': 'Could not extract sufficient text from document.'})
        
        evaluation = evaluate_proposal(proposal_text, proposal_type)
        if not evaluation:
            return jsonify({'success': False, 'error': 'Error evaluating proposal. Please try again.'})
        
        proposal = Proposal(
            submission_id=generate_submission_id(),
            author_name=author_name,
            author_email=author_email,
            book_title=book_title,
            proposal_type=proposal_type,
            ownership_confirmed=True,
            tier=evaluation.get('tier', 'C'),
            overall_score=evaluation.get('overall_score', 50),
            evaluation_json=json.dumps(evaluation),
            proposal_text=proposal_text[:50000],
            status='submitted'
        )
        
        db.session.add(proposal)
        db.session.commit()
        
        try:
            if send_author_notification(proposal):
                proposal.author_email_sent = True
            if send_team_notification(proposal):
                proposal.team_email_sent = True
            db.session.commit()
        except Exception as email_error:
            print(f"Email error (non-fatal): {email_error}")
        
        return jsonify({
            'success': True,
            'proposal_id': proposal.submission_id
        })
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'An unexpected error occurred. Please try again.'})


@app.route('/results/<submission_id>')
def results(submission_id):
    """Public results page for authors"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    return render_template('results.html', proposal=proposal, evaluation=evaluation)


@app.route('/download/<submission_id>')
def download_pdf(submission_id):
    """Download PDF report"""
    proposal = Proposal.query.filter_by(submission_id=submission_id).first_or_404()
    
    pdf_content = generate_pdf_report(proposal)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
        f.write(pdf_content)
        temp_path = f.name
    
    return send_file(
        temp_path,
        as_attachment=True,
        download_name=f"Book_Proposal_Evaluation_{proposal.submission_id}.pdf",
        mimetype='application/pdf'
    )


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


# Temporary route to reset admin password - DELETE AFTER USE
@app.route('/reset-admin-temp/<password>')
def reset_admin_temp(password):
    """Temporary route to reset admin password. DELETE THIS AFTER USE."""
    user = AdminUser.query.filter_by(email='anna@writeitgreat.com').first()
    if not user:
        user = AdminUser(email='anna@writeitgreat.com', name='Anna')
        db.session.add(user)
    user.set_password(password)
    db.session.commit()
    return f"Password for anna@writeitgreat.com set to: {password}. DELETE THIS ROUTE!"


# ============================================================================
# CLI COMMANDS
# ============================================================================

@app.cli.command('init-db')
def init_db():
    """Initialize the database"""
    db.create_all()
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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
