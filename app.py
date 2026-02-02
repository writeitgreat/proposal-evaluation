#!/usr/bin/env python3
"""
Write It Great - Book Proposal Evaluation System
A self-contained Heroku application for evaluating book proposals.
"""

import os
import json
import tempfile
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, url_for
from werkzeug.utils import secure_filename

from evaluate import evaluate_proposal, extract_text_from_pdf
from report_generator import generate_pdf_report
from email_service import send_author_notification, send_team_notification

app = Flask(__name__)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
ALLOWED_EXTENSIONS = {'pdf'}

# Storage for reports (in production, use S3 or similar)
REPORTS_DIR = tempfile.mkdtemp()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Main submission form."""
    return render_template('index.html')


# Note: Terms and NDA are displayed as modals in index.html
# No separate pages needed


@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    """
    Evaluate a book proposal submission.
    
    Expected form data:
    - author_name: str
    - author_email: str
    - book_title: str
    - proposal_type: 'full' | 'marketing_only' | 'no_marketing'
    - agree_terms: 'on'
    - agree_nda: 'on'
    - proposal_file: PDF file
    """
    try:
        # Validate required fields
        required_fields = ['author_name', 'author_email', 'book_title', 'proposal_type']
        for field in required_fields:
            if not request.form.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate checkboxes
        if not request.form.get('agree_terms'):
            return jsonify({'error': 'You must agree to the Terms and Conditions'}), 400
        if not request.form.get('agree_nda'):
            return jsonify({'error': 'You must agree to the NDA'}), 400
        
        # Validate file
        if 'proposal_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['proposal_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are accepted'}), 400
        
        # Extract form data
        author_name = request.form['author_name'].strip()
        author_email = request.form['author_email'].strip()
        book_title = request.form['book_title'].strip()
        proposal_type = request.form['proposal_type']
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        temp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}_{filename}")
        file.save(temp_path)
        
        try:
            # Extract text from PDF
            proposal_text = extract_text_from_pdf(temp_path)
            
            if len(proposal_text.strip()) < 200:
                return jsonify({
                    'error': 'Could not extract sufficient text from the PDF. Please ensure it is not image-based or encrypted.'
                }), 400
            
            # Evaluate the proposal
            evaluation = evaluate_proposal(
                proposal_text=proposal_text,
                proposal_type=proposal_type,
                author_name=author_name,
                book_title=book_title
            )
            
            # Generate unique submission ID
            submission_id = f"WIG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            evaluation['submission_id'] = submission_id
            evaluation['author_name'] = author_name
            evaluation['author_email'] = author_email
            evaluation['book_title'] = book_title
            evaluation['proposal_type'] = proposal_type
            evaluation['submitted_at'] = datetime.utcnow().isoformat()
            
            # Generate PDF report
            report_filename = f"{submission_id}_feedback.pdf"
            report_path = os.path.join(REPORTS_DIR, report_filename)
            generate_pdf_report(evaluation, report_path)
            
            # Store evaluation data
            eval_path = os.path.join(REPORTS_DIR, f"{submission_id}_data.json")
            with open(eval_path, 'w') as f:
                json.dump(evaluation, f, indent=2)
            
            # Send emails
            try:
                send_team_notification(evaluation, report_path)
                # Note: We don't auto-send to author - they download directly
            except Exception as e:
                print(f"Email notification failed: {e}")
                # Don't fail the whole request if email fails
            
            # Return success with download URL
            return jsonify({
                'success': True,
                'submission_id': submission_id,
                'tier': evaluation['tier'],
                'total_score': evaluation['total_score'],
                'executive_summary': evaluation['executive_summary'],
                'download_url': url_for('download_report', submission_id=submission_id),
                'scores': evaluation['scores']
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        print(f"Evaluation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'An error occurred during evaluation: {str(e)}'}), 500


@app.route('/api/report/<submission_id>')
def download_report(submission_id):
    """Download the PDF feedback report."""
    report_path = os.path.join(REPORTS_DIR, f"{submission_id}_feedback.pdf")
    
    if not os.path.exists(report_path):
        return jsonify({'error': 'Report not found'}), 404
    
    return send_file(
        report_path,
        as_attachment=True,
        download_name=f"Write_It_Great_Proposal_Feedback_{submission_id}.pdf",
        mimetype='application/pdf'
    )


@app.route('/results/<submission_id>')
def results(submission_id):
    """Results page showing evaluation summary."""
    eval_path = os.path.join(REPORTS_DIR, f"{submission_id}_data.json")
    
    if not os.path.exists(eval_path):
        return render_template('error.html', message='Evaluation not found'), 404
    
    with open(eval_path, 'r') as f:
        evaluation = json.load(f)
    
    return render_template('results.html', evaluation=evaluation)


@app.route('/health')
def health():
    """Health check endpoint for Heroku."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
