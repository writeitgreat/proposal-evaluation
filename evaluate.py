#!/usr/bin/env python3
"""
Book proposal evaluation using OpenAI GPT-4o.
"""

import os
import json
import fitz  # PyMuPDF
from docx import Document
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyMuPDF."""
    doc = fitz.open(pdf_path)
    text_content = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            text_content.append(f"--- Page {page_num + 1} ---\n{text}")
    doc.close()
    return "\n\n".join(text_content)


def extract_text_from_docx(docx_path):
    """Extract text from Word document."""
    doc = Document(docx_path)
    text_content = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_content.append(para.text)
    return "\n\n".join(text_content)


def determine_tier(score):
    """Determine tier from score."""
    if score >= 85:
        return 'A'
    elif score >= 70:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'


def evaluate_proposal_with_openai(proposal_text, proposal_type, author_name, book_title):
    """
    Evaluate proposal using OpenAI GPT-4o.
    
    Args:
        proposal_text: Extracted text from the proposal
        proposal_type: 'full', 'marketing_only', or 'no_marketing'
        author_name: Name of the author
        book_title: Title of the book
    
    Returns:
        dict with evaluation results including scores, tier, and recommendations
    """
    
    # Weight configurations based on proposal type
    if proposal_type == 'marketing_only':
        weight_instruction = """
You are evaluating ONLY the Marketing & Platform section.
All other categories (Overview, Credentials, Comps, Writing, Outline, Completeness) should be scored as 0.
The Marketing score will be the total score.
"""
        weights = {'Marketing': 1.0}
    elif proposal_type == 'no_marketing':
        weight_instruction = """
This proposal does NOT include a Marketing section.
Score Marketing as 0.
Evaluate all other sections and weight them accordingly:
- Overview: 20%
- Credentials: 20%  
- Comps: 15%
- Writing: 20%
- Outline: 15%
- Completeness: 10%
"""
        weights = {
            'Overview': 0.20,
            'Credentials': 0.20,
            'Comps': 0.15,
            'Writing': 0.20,
            'Outline': 0.15,
            'Completeness': 0.10
        }
    else:  # full
        weight_instruction = """
Evaluate all sections with these weights:
- Overview: 15%
- Credentials: 15%
- Marketing: 20%
- Comps: 10%
- Writing: 20%
- Outline: 10%
- Completeness: 10%
"""
        weights = {
            'Overview': 0.15,
            'Credentials': 0.15,
            'Marketing': 0.20,
            'Comps': 0.10,
            'Writing': 0.20,
            'Outline': 0.10,
            'Completeness': 0.10
        }

    system_prompt = f"""You are an expert literary agent evaluating book proposals for Write It Great LLC, an elite ghostwriting and publishing services firm.

{weight_instruction}

For each category you evaluate, provide:
1. A score from 0-100
2. Detailed analysis with specific examples from the proposal
3. Strengths (bullet points)
4. Areas for improvement (bullet points)

Also provide:
- RED FLAGS: Any serious concerns (missing platform, no writing samples, unrealistic expectations, etc.)
- ACTION ITEMS: Numbered list of specific steps the author should take
- ADVANCE ESTIMATE: Realistic advance range based on the proposal quality and market

Respond with a JSON object in this exact format:
{{
    "scores": {{
        "Overview": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Credentials": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Marketing": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Comps": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Writing": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Outline": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}},
        "Completeness": {{"score": 0, "analysis": "", "strengths": [], "improvements": []}}
    }},
    "red_flags": ["flag1", "flag2"],
    "action_items": ["1. First action", "2. Second action"],
    "advance_estimate": {{
        "low": 5000,
        "high": 15000,
        "confidence": "medium",
        "reasoning": "explanation"
    }},
    "overall_summary": "2-3 paragraph summary of the proposal's strengths and potential"
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please evaluate this book proposal:\n\nAuthor: {author_name}\nTitle: {book_title}\n\n---\n\n{proposal_text[:50000]}"}
        ],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )
    
    evaluation = json.loads(response.choices[0].message.content)
    
    # Calculate weighted score
    total_score = 0
    for category, weight in weights.items():
        if category in evaluation.get('scores', {}):
            total_score += evaluation['scores'][category].get('score', 0) * weight
    
    evaluation['total_score'] = round(total_score, 2)
    evaluation['tier'] = determine_tier(total_score)
    evaluation['weights_used'] = weights
    
    return evaluation
