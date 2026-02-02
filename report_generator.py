#!/usr/bin/env python3
"""
PDF Report Generator for Write It Great Proposal Evaluations
Generates branded PDF feedback reports.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
import os
from datetime import datetime

# Brand colors
BRAND_BLACK = colors.HexColor('#1a1a1a')
BRAND_GOLD = colors.HexColor('#c9a962')
BRAND_DARK_GRAY = colors.HexColor('#2d2d2d')
BRAND_LIGHT_GRAY = colors.HexColor('#f5f5f5')
BRAND_WHITE = colors.white

# Tier colors
TIER_COLORS = {
    'A': colors.HexColor('#2e7d32'),  # Green
    'B': colors.HexColor('#1976d2'),  # Blue
    'C': colors.HexColor('#f57c00'),  # Orange
    'D': colors.HexColor('#d32f2f'),  # Red
}


def get_tier_description(tier):
    descriptions = {
        'A': 'Exceptional - Ready for top-tier publishers',
        'B': 'Strong - Minor improvements recommended',
        'C': 'Promising - Significant work needed',
        'D': 'Needs Development - Major revisions required'
    }
    return descriptions.get(tier, 'Unknown')


def create_styles():
    """Create custom paragraph styles."""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='BrandTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=BRAND_BLACK,
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=BRAND_BLACK,
        spaceBefore=20,
        spaceAfter=10,
        fontName='Helvetica-Bold',
        borderPadding=5,
        backColor=BRAND_LIGHT_GRAY
    ))
    
    styles.add(ParagraphStyle(
        name='SubHeader',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=BRAND_DARK_GRAY,
        spaceBefore=10,
        spaceAfter=5,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='BodyText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=BRAND_BLACK,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        leading=14
    ))
    
    styles.add(ParagraphStyle(
        name='BulletPoint',
        parent=styles['Normal'],
        fontSize=10,
        textColor=BRAND_BLACK,
        leftIndent=20,
        spaceAfter=4
    ))
    
    styles.add(ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.gray,
        alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name='TierBadge',
        parent=styles['Heading1'],
        fontSize=48,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    ))
    
    return styles


def generate_pdf_report(evaluation, output_path):
    """
    Generate a branded PDF feedback report.
    
    Args:
        evaluation: dict containing evaluation results
        output_path: path to save the PDF
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )
    
    styles = create_styles()
    story = []
    
    # Header
    story.append(Paragraph("WRITE IT GREAT", styles['BrandTitle']))
    story.append(Paragraph("Book Proposal Evaluation Report", styles['BodyText']))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_GOLD))
    story.append(Spacer(1, 20))
    
    # Submission Info
    info_data = [
        ['Submission ID:', evaluation.get('submission_id', 'N/A')],
        ['Book Title:', evaluation.get('book_title', 'N/A')],
        ['Author:', evaluation.get('author_name', 'N/A')],
        ['Evaluation Date:', datetime.now().strftime('%B %d, %Y')],
        ['Proposal Type:', evaluation.get('proposal_type', 'full').replace('_', ' ').title()],
    ]
    
    info_table = Table(info_data, colWidths=[1.5*inch, 4.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), BRAND_BLACK),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Overall Score and Tier
    tier = evaluation.get('tier', 'C')
    tier_color = TIER_COLORS.get(tier, colors.gray)
    total_score = evaluation.get('total_score', 0)
    
    score_data = [
        [
            Paragraph(f"<font color='{tier_color.hexval()}'><b>TIER {tier}</b></font>", 
                     ParagraphStyle('TierStyle', fontSize=36, alignment=TA_CENTER, fontName='Helvetica-Bold')),
            Paragraph(f"<b>{total_score}/100</b>", 
                     ParagraphStyle('ScoreStyle', fontSize=36, alignment=TA_CENTER, fontName='Helvetica-Bold'))
        ],
        [
            Paragraph(get_tier_description(tier), 
                     ParagraphStyle('DescStyle', fontSize=10, alignment=TA_CENTER, textColor=colors.gray)),
            Paragraph("Overall Score", 
                     ParagraphStyle('LabelStyle', fontSize=10, alignment=TA_CENTER, textColor=colors.gray))
        ]
    ]
    
    score_table = Table(score_data, colWidths=[3*inch, 3*inch])
    score_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (0, -1), 1, tier_color),
        ('BOX', (1, 0), (1, -1), 1, BRAND_GOLD),
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f8f8f8')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#f8f8f8')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 20))
    
    # Executive Summary
    story.append(Paragraph("EXECUTIVE SUMMARY", styles['SectionHeader']))
    story.append(Paragraph(evaluation.get('executive_summary', 'No summary available.'), styles['BodyText']))
    story.append(Spacer(1, 10))
    
    # Score Breakdown Table
    story.append(Paragraph("SCORE BREAKDOWN", styles['SectionHeader']))
    
    scores = evaluation.get('scores', {})
    weights = evaluation.get('weights_used', {})
    
    score_breakdown = [
        ['Category', 'Weight', 'Score', 'Weighted'],
        ['Marketing & Platform', f"{int(weights.get('marketing', 0.30)*100)}%", 
         f"{scores.get('marketing', 0)}/100", f"{scores.get('marketing', 0) * weights.get('marketing', 0.30):.1f}"],
        ['Overview & Concept', f"{int(weights.get('overview', 0.20)*100)}%", 
         f"{scores.get('overview', 0)}/100", f"{scores.get('overview', 0) * weights.get('overview', 0.20):.1f}"],
        ['Author Credentials', f"{int(weights.get('credentials', 0.15)*100)}%", 
         f"{scores.get('credentials', 0)}/100", f"{scores.get('credentials', 0) * weights.get('credentials', 0.15):.1f}"],
        ['Comparative Titles', f"{int(weights.get('comps', 0.15)*100)}%", 
         f"{scores.get('comps', 0)}/100", f"{scores.get('comps', 0) * weights.get('comps', 0.15):.1f}"],
        ['Sample Writing', f"{int(weights.get('writing', 0.10)*100)}%", 
         f"{scores.get('writing', 0)}/100", f"{scores.get('writing', 0) * weights.get('writing', 0.10):.1f}"],
        ['Book Outline', f"{int(weights.get('outline', 0.05)*100)}%", 
         f"{scores.get('outline', 0)}/100", f"{scores.get('outline', 0) * weights.get('outline', 0.05):.1f}"],
        ['Completeness', f"{int(weights.get('completeness', 0.05)*100)}%", 
         f"{scores.get('completeness', 0)}/100", f"{scores.get('completeness', 0) * weights.get('completeness', 0.05):.1f}"],
        ['TOTAL', '100%', '', f"{total_score}"],
    ]
    
    breakdown_table = Table(score_breakdown, colWidths=[2.5*inch, 1*inch, 1.25*inch, 1.25*inch])
    breakdown_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_DARK_GRAY),
        ('TEXTCOLOR', (0, 0), (-1, 0), BRAND_WHITE),
        ('BACKGROUND', (0, -1), (-1, -1), BRAND_LIGHT_GRAY),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 20))
    
    # Top Strengths
    story.append(Paragraph("TOP STRENGTHS", styles['SectionHeader']))
    for i, strength in enumerate(evaluation.get('top_3_strengths', []), 1):
        story.append(Paragraph(f"<b>{i}.</b> {strength}", styles['BulletPoint']))
    story.append(Spacer(1, 10))
    
    # Top Improvements
    story.append(Paragraph("KEY AREAS FOR IMPROVEMENT", styles['SectionHeader']))
    for i, improvement in enumerate(evaluation.get('top_3_improvements', []), 1):
        story.append(Paragraph(f"<b>{i}.</b> {improvement}", styles['BulletPoint']))
    story.append(Spacer(1, 10))
    
    # Recommended Next Steps
    story.append(Paragraph("RECOMMENDED NEXT STEPS", styles['SectionHeader']))
    for i, step in enumerate(evaluation.get('recommended_next_steps', []), 1):
        story.append(Paragraph(f"<b>{i}.</b> {step}", styles['BulletPoint']))
    story.append(Spacer(1, 20))
    
    # Detailed Category Feedback
    story.append(Paragraph("DETAILED CATEGORY FEEDBACK", styles['SectionHeader']))
    
    category_names = {
        'marketing': 'Marketing & Platform',
        'overview': 'Overview & Concept',
        'credentials': 'Author Credentials',
        'comps': 'Comparative Titles',
        'writing': 'Sample Writing',
        'outline': 'Book Outline',
        'completeness': 'Completeness'
    }
    
    category_feedback = evaluation.get('category_feedback', {})
    for cat_key, cat_name in category_names.items():
        feedback = category_feedback.get(cat_key, {})
        cat_score = feedback.get('score', scores.get(cat_key, 0))
        
        story.append(Paragraph(f"{cat_name} ({cat_score}/100)", styles['SubHeader']))
        story.append(Paragraph(feedback.get('summary', 'No summary available.'), styles['BodyText']))
        
        strengths = feedback.get('strengths', [])
        if strengths:
            story.append(Paragraph("<b>Strengths:</b>", styles['BodyText']))
            for s in strengths[:3]:
                story.append(Paragraph(f"• {s}", styles['BulletPoint']))
        
        gaps = feedback.get('gaps', [])
        if gaps:
            story.append(Paragraph("<b>Areas for Improvement:</b>", styles['BodyText']))
            for g in gaps[:3]:
                story.append(Paragraph(f"• {g}", styles['BulletPoint']))
        
        story.append(Spacer(1, 10))
    
    # Coaching Upsell for C/D Tiers
    if tier in ['C', 'D']:
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_GOLD))
        story.append(Spacer(1, 10))
        
        upsell_style = ParagraphStyle(
            'Upsell',
            fontSize=11,
            textColor=BRAND_BLACK,
            alignment=TA_CENTER,
            spaceAfter=10,
            backColor=colors.HexColor('#fff8e1'),
            borderPadding=15
        )
        
        story.append(Paragraph(
            "<b>READY TO STRENGTHEN YOUR PROPOSAL?</b>",
            ParagraphStyle('UpsellHeader', fontSize=14, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=10)
        ))
        story.append(Paragraph(
            "Our team of expert ghostwriters and literary consultants can help you transform your proposal "
            "into a publisher-ready submission. Schedule a free consultation to discuss your book project.",
            styles['BodyText']
        ))
        story.append(Paragraph(
            "<b>Contact us: hello@writeitgreat.com</b>",
            ParagraphStyle('Contact', fontSize=11, alignment=TA_CENTER, spaceAfter=5)
        ))
        story.append(Paragraph(
            "www.writeitgreat.com",
            ParagraphStyle('Website', fontSize=10, alignment=TA_CENTER, textColor=BRAND_GOLD)
        ))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"© {datetime.now().year} Write It Great LLC. All rights reserved. This evaluation is confidential.",
        styles['Footer']
    ))
    story.append(Paragraph(
        "This AI-assisted evaluation is intended as guidance only and does not guarantee publishing success.",
        styles['Footer']
    ))
    
    # Build the PDF
    doc.build(story)
