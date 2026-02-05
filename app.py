#!/usr/bin/env python3
"""
Write It Great - Book Proposal Evaluation System
Updated with database storage, admin dashboard, and email to authors
"""

import os
import json
import tempfile
import uuid
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from evaluate import evaluate_proposal_with_openai, extract_text_from_pdf, extract_text_from_docx
from report_generator import generate_pdf_report
from email_service import send_report_to_author, send_team_notification

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

# Database Configuration
database_url = os.getenv('DATABASE_URL', 'sqlite:///proposals.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'

# Temp storage for PDFs (use /tmp for Heroku)
REPORTS_DIR = os.getenv('REPORTS_DIR', '/tmp/reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}


# =============================================================================
# DATABASE MODELS
# =============================================================================

class AdminUser(UserMixin, db.Model):
    """Admin users who can access the dashboard."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Proposal(db.Model):
    """Book proposal submissions."""
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    # Author Information
    author_name = db.Column(db.String(200), nullable=False)
    author_email = db.Column(db.String(200), nullable=False)
    book_title = db.Column(db.String(500), nullable=False)
    proposal_type = db.Column(db.String(50), default='full')
    
    # Evaluation Results
    tier = db.Column(db.String(1))
    total_score = db.Column(db.Float)
    evaluation_json = db.Column(db.Text)
    
    # Status Tracking
    status = db.Column(db.String(50), default='new')
    status_notes = db.Column(db.Text)
    
    # Timestamps
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Files
    original_filename = db.Column(db.String(500))
    report_sent_at = db.Column(db.DateTime)
    
    @property
    def evaluation(self):
        if self.evaluation_json:
            return json.loads(self.evaluation_json)
        return None
    
    @property
    def status_display(self):
        status_map = {
            'new': '🆕 New',
            'read': '👁️ Read',
            'author_call_scheduled': '📅 Call Scheduled',
            'author_call_completed': '✅ Call Completed',
            'shopping': '🛒 Shopping with Publishers',
            'contract_sent': '📄 Contract Sent',
            'signed': '✍️ Signed',
            'declined': '❌ Declined',
            'archived': '📁 Archived'
        }
        return status_map.get(self.status, self.status)
    
    @property
    def tier_display(self):
        tier_map = {
            'A': '🟢 A-Tier',
            'B': '🔵 B-Tier',
            'C': '🟡 C-Tier',
            'D': '🔴 D-Tier'
        }
        return tier_map.get(self.tier, self.tier)


@login_manager.user_loader
def load_user(user_id):
    return AdminUser.query.get(int(user_id))


STATUS_OPTIONS = [
    ('new', '🆕 New'),
    ('read', '👁️ Read'),
    ('author_call_scheduled', '📅 Author Call Scheduled'),
    ('author_call_completed', '✅ Author Call Completed'),
    ('shopping', '🛒 Shopping with Publishers'),
    ('contract_sent', '📄 Contract Sent'),
    ('signed', '✍️ Signed'),
    ('declined', '❌ Declined'),
    ('archived', '📁 Archived')
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def determine_tier(score):
    if score >= 85:
        return 'A'
    elif score >= 70:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'


# =============================================================================
# PUBLIC ROUTES
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/api/evaluate', methods=['POST'])
def api_evaluate():
    author_name = request.form.get('author_name', '').strip()
    author_email = request.form.get('author_email', '').strip()
    book_title = request.form.get('book_title', '').strip()
    proposal_type = request.form.get('proposal_type', 'full')
    
    if not all([author_name, author_email, book_title]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if 'proposal_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['proposal_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Please upload PDF or Word document.'}), 400
    
    filename = secure_filename(file.filename)
    temp_path = os.path.join(REPORTS_DIR, f"temp_{uuid.uuid4()}_{filename}")
    file.save(temp_path)
    
    try:
        # Extract text
        if filename.lower().endswith('.pdf'):
            proposal_text = extract_text_from_pdf(temp_path)
        else:
            proposal_text = extract_text_from_docx(temp_path)
        
        if len(proposal_text.strip()) < 100:
            return jsonify({'error': 'Could not extract enough text from the file.'}), 400
        
        # Evaluate with OpenAI
        evaluation = evaluate_proposal_with_openai(proposal_text, proposal_type, author_name, book_title)
        
        # Create proposal record in database
        proposal = Proposal(
            author_name=author_name,
            author_email=author_email,
            book_title=book_title,
            proposal_type=proposal_type,
            tier=evaluation['tier'],
            total_score=evaluation['total_score'],
            evaluation_json=json.dumps(evaluation),
            original_filename=filename,
            status='new'
        )
        db.session.add(proposal)
        db.session.commit()
        
        # Generate PDF report
        pdf_path = generate_pdf_report(proposal.uuid, evaluation, author_name, book_title, REPORTS_DIR)
        
        # Send report to author's email
        email_sent = send_report_to_author(proposal, pdf_path)
        if email_sent:
            proposal.report_sent_at = datetime.utcnow()
            db.session.commit()
        
        # Notify team
        send_team_notification(proposal)
        
        # Clean up temp file
        os.remove(temp_path)
        
        return jsonify({
            'success': True,
            'proposal_id': proposal.uuid,
            'tier': evaluation['tier'],
            'total_score': evaluation['total_score'],
            'evaluation': evaluation,
            'email_sent': email_sent,
            'pdf_url': url_for('download_report', proposal_uuid=proposal.uuid)
        })
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"Evaluation error: {e}")
        return jsonify({'error': f'Evaluation failed: {str(e)}'}), 500


@app.route('/results/<proposal_uuid>')
def results(proposal_uuid):
    proposal = Proposal.query.filter_by(uuid=proposal_uuid).first_or_404()
    return render_template('results.html', proposal=proposal, evaluation=proposal.evaluation)


@app.route('/download/<proposal_uuid>')
def download_report(proposal_uuid):
    proposal = Proposal.query.filter_by(uuid=proposal_uuid).first_or_404()
    
    pdf_path = os.path.join(REPORTS_DIR, f"report_{proposal.uuid}.pdf")
    if not os.path.exists(pdf_path):
        pdf_path = generate_pdf_report(proposal.uuid, proposal.evaluation, 
                                       proposal.author_name, proposal.book_title, REPORTS_DIR)
    
    return send_file(pdf_path, 
                     as_attachment=True, 
                     download_name=f"Evaluation_Report_{proposal.book_title.replace(' ', '_')}.pdf")


# =============================================================================
# ADMIN ROUTES
# =============================================================================

@app.route('/admin')
@app.route('/admin/')
def admin_index():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        user = AdminUser.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('admin_login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    tier_filter = request.args.get('tier', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = Proposal.query
    
    if tier_filter:
        query = query.filter(Proposal.tier == tier_filter)
    
    if status_filter:
        query = query.filter(Proposal.status == status_filter)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Proposal.author_name.ilike(search_term),
                Proposal.book_title.ilike(search_term),
                Proposal.author_email.ilike(search_term)
            )
        )
    
    proposals = query.order_by(Proposal.submitted_at.desc()).all()
    
    stats = {
        'total': Proposal.query.count(),
        'new': Proposal.query.filter_by(status='new').count(),
        'a_tier': Proposal.query.filter_by(tier='A').count(),
        'b_tier': Proposal.query.filter_by(tier='B').count(),
        'c_tier': Proposal.query.filter_by(tier='C').count(),
        'd_tier': Proposal.query.filter_by(tier='D').count(),
        'shopping': Proposal.query.filter_by(status='shopping').count(),
    }
    
    return render_template('admin_dashboard.html', 
                           proposals=proposals, 
                           stats=stats,
                           status_options=STATUS_OPTIONS,
                           tier_filter=tier_filter,
                           status_filter=status_filter,
                           search=search)


@app.route('/admin/proposal/<int:proposal_id>')
@login_required
def admin_proposal_detail(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    return render_template('admin_proposal.html', 
                           proposal=proposal, 
                           evaluation=proposal.evaluation,
                           status_options=STATUS_OPTIONS)


@app.route('/admin/proposal/<int:proposal_id>/update', methods=['POST'])
@login_required
def admin_update_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    
    new_status = request.form.get('status')
    status_notes = request.form.get('status_notes', '')
    
    if new_status:
        proposal.status = new_status
    
    proposal.status_notes = status_notes
    db.session.commit()
    
    flash(f'Proposal updated: {proposal.status_display}', 'success')
    return redirect(url_for('admin_proposal_detail', proposal_id=proposal_id))


@app.route('/admin/proposal/<int:proposal_id>/resend-report', methods=['POST'])
@login_required
def admin_resend_report(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    
    pdf_path = os.path.join(REPORTS_DIR, f"report_{proposal.uuid}.pdf")
    if not os.path.exists(pdf_path):
        pdf_path = generate_pdf_report(proposal.uuid, proposal.evaluation,
                                       proposal.author_name, proposal.book_title, REPORTS_DIR)
    
    if send_report_to_author(proposal, pdf_path):
        proposal.report_sent_at = datetime.utcnow()
        db.session.commit()
        flash(f'Report sent to {proposal.author_email}', 'success')
    else:
        flash('Failed to send email. Check email configuration.', 'error')
    
    return redirect(url_for('admin_proposal_detail', proposal_id=proposal_id))


# =============================================================================
# CLI COMMANDS
# =============================================================================

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("Database initialized!")


@app.cli.command('create-admin')
def create_admin():
    import getpass
    
    email = input("Admin email: ").strip().lower()
    name = input("Admin name: ").strip()
    password = getpass.getpass("Password: ")
    
    if AdminUser.query.filter_by(email=email).first():
        print(f"Admin user {email} already exists!")
        return
    
    admin = AdminUser(email=email, name=name)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    
    print(f"Admin user {email} created successfully!")


@app.cli.command('setup-anna')
def setup_anna():
    email = 'anna@writeitgreat.com'
    
    if AdminUser.query.filter_by(email=email).first():
        print(f"Admin user {email} already exists!")
        return
    
    import secrets
    password = secrets.token_urlsafe(12)
    
    admin = AdminUser(email=email, name='Anna')
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    
    print(f"\nAdmin user created!")
    print(f"Email: {email}")
    print(f"Password: {password}")
    print(f"\nSave this password!")


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error_code=404, error_message="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error_code=500, error_message="Something went wrong"), 500


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
