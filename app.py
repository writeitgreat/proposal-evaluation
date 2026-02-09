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
    proposal_type = db.Column(db.String(50), default='full')  # full, marketing_only, no_marketing
    ownership_confirmed = db.Column(db.Boolean, default=True)
    
    # Evaluation results
    tier = db.Column(db.String(10))  # A, B, C, D
    overall_score = db.Column(db.Float)
    evaluation_json = db.Column(db.Text)  # Full evaluation data as JSON
    proposal_text = db.Column(db.Text)  # Extracted text from document
    
    # Status tracking
    status = db.Column(db.String(50), default='submitted')
    notes = db.Column(db.Text)  # Internal team notes
    
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
    
    system_prompt = """You are an expert book proposal evaluator for Write It Great, an elite ghostwriting and publishing services firm. You have decades of experience evaluating non-fiction book proposals.

Evaluate the proposal and provide scores and feedback for each category. Be honest, constructive, and specific.

Return a JSON object with this exact structure:
{
    "tier": "A" or "B" or "C" or "D",
    "overall_score": 0-100,
    "summary": "2-3 sentence overall assessment",
    "red_flags": ["list of concerns"],
    "strengths": ["list of strengths"],
    "advance_estimate": {
        "low": 0,
        "high": 0,
        "notes": "explanation of advance estimate"
    },
    "categories": {
        "concept": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        },
        "market": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        },
        "author_platform": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        },
        "writing_sample": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        },
        "marketing_plan": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        },
        "competitive_analysis": {
            "score": 0-100,
            "feedback": "detailed feedback",
            "priority_actions": ["specific actions to improve"]
        }
    },
    "next_steps": ["prioritized list of 3-5 most important next steps"]
}

TIER DEFINITIONS:
- A-Tier (80-100): Publisher-ready or near-ready. Strong concept, established platform, clear market.
- B-Tier (60-79): Promising with work needed. Good foundation but needs development in 1-2 key areas.
- C-Tier (40-59): Significant development needed. Multiple areas require substantial work.
- D-Tier (0-39): Not ready for traditional publishing. Consider alternative paths.

ADVANCE ESTIMATES (for non-fiction):
- A-Tier: $15,000-$30,000 (only for established platform authors)
- B-Tier: $0-$10,000 (most first-time authors)
- C-Tier: $0-$5,000 (if any)
- D-Tier: Self-publishing recommended

Be realistic about advances. Most first-time non-fiction authors receive $0-$10K even with good proposals."""

    # Adjust for proposal type
    type_instructions = ""
    if proposal_type == 'marketing_only':
        type_instructions = "\n\nNOTE: This is a MARKETING-ONLY submission. Focus 100% of your evaluation on the marketing plan and author platform. Set other category scores to 0."
    elif proposal_type == 'no_marketing':
        type_instructions = "\n\nNOTE: This submission EXCLUDES marketing materials. Do not penalize for missing marketing - score marketing_plan as 0 but redistribute weights to other categories."

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_prompt + type_instructions},
                {"role": "user", "content": f"Please evaluate this book proposal:\n\n{proposal_text[:15000]}"}  # Limit to 15k chars
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        evaluation = json.loads(response.choices[0].message.content)
        return evaluation
    except Exception as e:
        print(f"Evaluation error: {e}")
        return None


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
            <img src="https://writeitgreat.com/logo.png" alt="Write It Great" style="max-width: 200px; margin-bottom: 20px;">
            
            <h2 style="color: #4a2c5a;">Your Book Proposal Evaluation Results</h2>
            
            <p>Dear {proposal.author_name},</p>
            
            <p>Thank you for submitting your book proposal for <strong>"{proposal.book_title}"</strong> to Write It Great.</p>
            
            <div style="background: #f8f6f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #4a2c5a;">Evaluation Summary</h3>
                <p><strong>Classification:</strong> {proposal.tier}-Tier</p>
                <p><strong>Overall Score:</strong> {proposal.overall_score:.0f}/100</p>
                <p><strong>Summary:</strong> {evaluation.get('summary', 'See attached report for details.')}</p>
            </div>
            
            <p>Your complete evaluation report is attached to this email as a PDF. This includes detailed feedback on each section of your proposal and recommended next steps.</p>
            
            <h3 style="color: #4a2c5a;">What Happens Next?</h3>
            <p>A member of our team will review your evaluation and reach out within 3-5 business days to discuss potential next steps and how Write It Great can help you achieve your publishing goals.</p>
            
            <p>In the meantime, please review the attached report and feel free to reach out with any questions.</p>
            
            <p>Best regards,<br>
            <strong>The Write It Great Team</strong></p>
            
            <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
            <p style="font-size: 12px; color: #666;">
                Write It Great | Elite Ghostwriting & Publishing Services<br>
                <a href="https://writeitgreat.com">writeitgreat.com</a>
            </p>
        </div>
    </body>
    </html>
    """
    
    # Generate PDF report
    pdf_content = generate_pdf_report(proposal)
    attachments = [(f"Book_Proposal_Evaluation_{proposal.submission_id}.pdf", pdf_content)]
    
    return send_email(proposal.author_email, subject, html_content, attachments)


def send_team_notification(proposal):
    """Send notification to team about new submission"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    
    subject = f"[{proposal.tier}-Tier] New Proposal: {proposal.book_title}"
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #4a2c5a;">New Book Proposal Submission</h2>
            
            <div style="background: #f8f6f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #4a2c5a;">{proposal.tier}-Tier Proposal</h3>
                <table style="width: 100%;">
                    <tr>
                        <td><strong>Author:</strong></td>
                        <td>{proposal.author_name}</td>
                    </tr>
                    <tr>
                        <td><strong>Email:</strong></td>
                        <td><a href="mailto:{proposal.author_email}">{proposal.author_email}</a></td>
                    </tr>
                    <tr>
                        <td><strong>Book Title:</strong></td>
                        <td>{proposal.book_title}</td>
                    </tr>
                    <tr>
                        <td><strong>Overall Score:</strong></td>
                        <td>{proposal.overall_score:.0f}/100</td>
                    </tr>
                    <tr>
                        <td><strong>Submitted:</strong></td>
                        <td>{proposal.submitted_at.strftime('%B %d, %Y at %I:%M %p')}</td>
                    </tr>
                </table>
            </div>
            
            <p><strong>Summary:</strong> {evaluation.get('summary', 'No summary available.')}</p>
            
            <p><a href="{os.environ.get('APP_URL', 'http://localhost:5000')}/admin/proposal/{proposal.submission_id}" 
                  style="display: inline-block; background: #4a2c5a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">
                View Full Proposal →
            </a></p>
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


def generate_pdf_report(proposal):
    """Generate PDF report for proposal"""
    evaluation = json.loads(proposal.evaluation_json) if proposal.evaluation_json else {}
    
    html = render_template('report_pdf.html', proposal=proposal, evaluation=evaluation)
    pdf = HTML(string=html).write_pdf()
    return pdf


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
        # Get form data
        author_name = request.form.get('author_name', '').strip()
        author_email = request.form.get('author_email', '').strip()
        book_title = request.form.get('book_title', '').strip()
        proposal_type = request.form.get('proposal_type', 'full')
        
        # Validate required fields
        if not all([author_name, author_email, book_title]):
            return jsonify({'success': False, 'error': 'Please fill in all required fields.'})
        
        # Get uploaded file
        file = request.files.get('proposal_file')
        if not file or file.filename == '':
            return jsonify({'success': False, 'error': 'Please upload your proposal document.'})
        
        # Extract text from file
        filename = secure_filename(file.filename).lower()
        if filename.endswith('.pdf'):
            proposal_text = extract_text_from_pdf(file)
        elif filename.endswith('.docx') or filename.endswith('.doc'):
            proposal_text = extract_text_from_docx(file)
        else:
            return jsonify({'success': False, 'error': 'Please upload a PDF or Word document (.pdf, .docx, .doc).'})
        
        if len(proposal_text.strip()) < 500:
            return jsonify({'success': False, 'error': 'Could not extract sufficient text from document. Please ensure your file is not corrupted or password-protected.'})
        
        # Evaluate proposal
        evaluation = evaluate_proposal(proposal_text, proposal_type)
        if not evaluation:
            return jsonify({'success': False, 'error': 'Error evaluating proposal. Please try again.'})
        
        # Create proposal record
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
            proposal_text=proposal_text[:50000],  # Store first 50k chars
            status='submitted'
        )
        
        db.session.add(proposal)
        db.session.commit()
        
        # Send emails (don't fail if email fails)
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
    
    # Create temp file
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
    
    # Stats
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
        # Update status
        new_status = request.form.get('status')
        if new_status and new_status in [s[0] for s in STATUS_OPTIONS]:
            proposal.status = new_status
        
        # Update notes
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
    
    # Check if user exists
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
    return render_template('error.html', 
                         error_code=404, 
                         error_message="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', 
                         error_code=500, 
                         error_message="Server error. Please try again."), 500


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
