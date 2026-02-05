#!/usr/bin/env python3
"""
PDF report generation using WeasyPrint.
"""

import os
from datetime import datetime
from weasyprint import HTML, CSS


def generate_pdf_report(proposal_uuid, evaluation, author_name, book_title, reports_dir):
    """
    Generate a PDF evaluation report.
    
    Args:
        proposal_uuid: Unique ID of the proposal
        evaluation: Dict with evaluation results
        author_name: Name of the author
        book_title: Title of the book
        reports_dir: Directory to save the PDF
    
    Returns:
        str: Path to the generated PDF file
    """
    
    # Determine tier styling
    tier = evaluation.get('tier', 'C')
    tier_colors = {
        'A': '#22c55e',
        'B': '#3b82f6',
        'C': '#f59e0b',
        'D': '#ef4444'
    }
    tier_color = tier_colors.get(tier, '#f59e0b')
    
    # Build scores HTML
    scores_html = ""
    for category, data in evaluation.get('scores', {}).items():
        score = data.get('score', 0)
        if score > 0:
            analysis = data.get('analysis', '')
            strengths = data.get('strengths', [])
            improvements = data.get('improvements', [])
            
            strengths_html = ""
            if strengths:
                strengths_html = "<p style='color: #22c55e; font-size: 10pt; font-weight: bold; margin-top: 10pt;'>STRENGTHS</p><ul>"
                for s in strengths:
                    strengths_html += f"<li>{s}</li>"
                strengths_html += "</ul>"
            
            improvements_html = ""
            if improvements:
                improvements_html = "<p style='color: #f59e0b; font-size: 10pt; font-weight: bold; margin-top: 10pt;'>AREAS FOR IMPROVEMENT</p><ul>"
                for i in improvements:
                    improvements_html += f"<li>{i}</li>"
                improvements_html += "</ul>"
            
            scores_html += f"""
            <div class="score-box">
                <div style="display: flex; justify-content: space-between; margin-bottom: 8pt;">
                    <strong>{category}</strong>
                    <span style="color: #6B21A8; font-weight: bold;">{score}/100</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {score}%;"></div>
                </div>
                <p style="color: #555; font-size: 10pt;">{analysis}</p>
                {strengths_html}
                {improvements_html}
            </div>
            """
    
    # Build red flags HTML
    red_flags_html = ""
    if evaluation.get('red_flags'):
        red_flags_html = "<h2>⚠️ Red Flags</h2>"
        for flag in evaluation['red_flags']:
            red_flags_html += f'<div class="red-flag">{flag}</div>'
    
    # Build action items HTML
    action_items_html = ""
    if evaluation.get('action_items'):
        action_items_html = "<h2>📋 Recommended Action Items</h2>"
        for item in evaluation['action_items']:
            action_items_html += f'<div class="action-item">{item}</div>'
    
    # Build advance estimate HTML
    advance_html = ""
    if evaluation.get('advance_estimate'):
        est = evaluation['advance_estimate']
        low = "{:,}".format(est.get('low', 0))
        high = "{:,}".format(est.get('high', 0))
        confidence = est.get('confidence', 'medium').capitalize()
        reasoning = est.get('reasoning', '')
        advance_html = f"""
        <h2>💰 Estimated Advance Range</h2>
        <div class="advance-box">
            <div class="advance-range">${low} - ${high}</div>
            <p style="color: #666; margin-top: 8pt;">Confidence: {confidence}</p>
            <p style="color: #666; margin-top: 8pt; font-size: 10pt;">{reasoning}</p>
        </div>
        """
    
    # Overall summary
    summary = evaluation.get('overall_summary', '')
    summary_html = ""
    if summary:
        summary_html = f"""
        <h2>Executive Summary</h2>
        <p style="color: #555;">{summary}</p>
        """
    
    total_score = evaluation.get('total_score', 0)
    generated_date = datetime.utcnow().strftime('%B %d, %Y')
    current_year = datetime.utcnow().year
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Book Proposal Evaluation - {book_title}</title>
        <style>
            @page {{
                size: letter;
                margin: 0.75in;
                @bottom-center {{
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 9pt;
                    color: #666;
                }}
            }}
            
            body {{
                font-family: 'Helvetica Neue', Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.5;
                color: #333;
            }}
            
            .header {{
                text-align: center;
                margin-bottom: 30pt;
                padding-bottom: 15pt;
                border-bottom: 2px solid #6B21A8;
            }}
            
            .logo-text {{
                font-size: 24pt;
                font-weight: bold;
                color: #6B21A8;
                letter-spacing: 1pt;
            }}
            
            .subtitle {{
                color: #666;
                font-size: 10pt;
                margin-top: 5pt;
            }}
            
            h1 {{
                font-size: 22pt;
                color: #1a1a1a;
                margin: 20pt 0 10pt;
            }}
            
            h2 {{
                font-size: 14pt;
                color: #6B21A8;
                margin: 20pt 0 10pt;
                padding-bottom: 5pt;
                border-bottom: 1px solid #ddd;
            }}
            
            .tier-badge {{
                display: inline-block;
                padding: 8pt 20pt;
                font-size: 18pt;
                font-weight: bold;
                color: white;
                border-radius: 8pt;
                background: {tier_color};
                margin-bottom: 15pt;
            }}
            
            .info-table {{
                width: 100%;
                margin: 15pt 0;
                border-collapse: collapse;
            }}
            
            .info-table td {{
                padding: 8pt;
                border-bottom: 1px solid #eee;
            }}
            
            .info-table td:first-child {{
                width: 120pt;
                color: #666;
                font-weight: 500;
            }}
            
            .score-box {{
                background: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 8pt;
                padding: 15pt;
                margin: 10pt 0;
            }}
            
            .progress-bar {{
                height: 8pt;
                background: #e0e0e0;
                border-radius: 4pt;
                overflow: hidden;
                margin-bottom: 10pt;
            }}
            
            .progress-fill {{
                height: 100%;
                background: linear-gradient(90deg, #6B21A8, #A855F7);
            }}
            
            ul {{
                padding-left: 15pt;
                margin: 5pt 0;
            }}
            
            ul li {{
                margin: 4pt 0;
                color: #555;
            }}
            
            .red-flag {{
                background: #fef2f2;
                border: 1px solid #ef4444;
                border-radius: 6pt;
                padding: 10pt;
                margin: 8pt 0;
                color: #dc2626;
            }}
            
            .action-item {{
                background: #eff6ff;
                border: 1px solid #3b82f6;
                border-radius: 6pt;
                padding: 10pt;
                margin: 8pt 0;
                color: #2563eb;
            }}
            
            .advance-box {{
                background: linear-gradient(135deg, #f3e8ff, #ede9fe);
                border: 2px solid #6B21A8;
                border-radius: 8pt;
                padding: 20pt;
                text-align: center;
                margin: 15pt 0;
            }}
            
            .advance-range {{
                font-size: 20pt;
                font-weight: bold;
                color: #6B21A8;
            }}
            
            .footer {{
                margin-top: 30pt;
                padding-top: 15pt;
                border-top: 1px solid #ddd;
                text-align: center;
                color: #888;
                font-size: 9pt;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo-text">WRITE IT GREAT</div>
            <div class="subtitle">Professional Book Proposal Evaluation</div>
        </div>
        
        <div style="text-align: center; margin-bottom: 30pt;">
            <span class="tier-badge">{tier}-TIER</span>
            <h1>{book_title}</h1>
            <p style="color: #666; font-size: 14pt;">by {author_name}</p>
        </div>
        
        <table class="info-table">
            <tr>
                <td>Total Score</td>
                <td><strong style="font-size: 14pt; color: #6B21A8;">{int(total_score)}/100</strong></td>
            </tr>
            <tr>
                <td>Classification</td>
                <td>{tier}-Tier Proposal</td>
            </tr>
            <tr>
                <td>Evaluated On</td>
                <td>{generated_date}</td>
            </tr>
        </table>
        
        {summary_html}
        
        <h2>Detailed Evaluation</h2>
        {scores_html}
        
        {red_flags_html}
        
        {action_items_html}
        
        {advance_html}
        
        <div class="footer">
            <p>This evaluation was generated by Write It Great LLC</p>
            <p>www.writeitgreat.com | hello@writeitgreat.com</p>
            <p style="margin-top: 8pt;">© {current_year} Write It Great LLC. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    
    # Generate PDF
    pdf_path = os.path.join(reports_dir, f"report_{proposal_uuid}.pdf")
    HTML(string=html_content).write_pdf(pdf_path)
    
    return pdf_path
