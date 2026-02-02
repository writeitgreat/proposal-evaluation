#!/usr/bin/env python3
"""
Book Proposal Evaluation Engine
Uses OpenAI to evaluate book proposals with different scoring modes.
"""

import os
import json
import fitz  # PyMuPDF
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Scoring weights for full proposals
FULL_WEIGHTS = {
    'marketing': 0.30,      # 30%
    'overview': 0.20,       # 20%
    'credentials': 0.15,    # 15%
    'comps': 0.15,          # 15%
    'writing': 0.10,        # 10%
    'outline': 0.05,        # 5%
    'completeness': 0.05    # 5%
}

# For marketing_only: only marketing matters
MARKETING_ONLY_WEIGHTS = {
    'marketing': 1.00,
    'overview': 0.00,
    'credentials': 0.00,
    'comps': 0.00,
    'writing': 0.00,
    'outline': 0.00,
    'completeness': 0.00
}

# For no_marketing: redistribute weights excluding marketing
NO_MARKETING_WEIGHTS = {
    'marketing': 0.00,
    'overview': 0.29,       # 20/(100-30) * 100 ≈ 29%
    'credentials': 0.21,    # 15/(100-30) * 100 ≈ 21%
    'comps': 0.21,          # 15/(100-30) * 100 ≈ 21%
    'writing': 0.14,        # 10/(100-30) * 100 ≈ 14%
    'outline': 0.07,        # 5/(100-30) * 100 ≈ 7%
    'completeness': 0.08    # 5/(100-30) * 100 ≈ 8%
}


def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file."""
    doc = fitz.open(pdf_path)
    text_content = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if text.strip():
            text_content.append(f"--- Page {page_num + 1} ---\n{text}")
    
    doc.close()
    return "\n\n".join(text_content)


def get_weights_for_type(proposal_type):
    """Get the appropriate weights based on proposal type."""
    if proposal_type == 'marketing_only':
        return MARKETING_ONLY_WEIGHTS
    elif proposal_type == 'no_marketing':
        return NO_MARKETING_WEIGHTS
    else:  # 'full'
        return FULL_WEIGHTS


def calculate_weighted_score(scores, proposal_type):
    """Calculate the weighted total score based on proposal type."""
    weights = get_weights_for_type(proposal_type)
    
    total = 0
    for category, weight in weights.items():
        score = scores.get(category, 0)
        total += score * weight
    
    return round(total, 2)


def determine_tier(score):
    """Determine the tier based on total score."""
    if score >= 85:
        return 'A'
    elif score >= 70:
        return 'B'
    elif score >= 50:
        return 'C'
    else:
        return 'D'


def evaluate_proposal(proposal_text, proposal_type, author_name, book_title):
    """
    Evaluate a book proposal using OpenAI.
    
    Args:
        proposal_text: The extracted text from the proposal PDF
        proposal_type: 'full', 'marketing_only', or 'no_marketing'
        author_name: Name of the author
        book_title: Title of the book
    
    Returns:
        dict with evaluation results
    """
    
    # Determine which categories to evaluate based on proposal type
    if proposal_type == 'marketing_only':
        evaluation_focus = """
You are evaluating ONLY the Marketing & Platform section of this proposal.
All other categories should be scored as 0 since they were not submitted.
Focus entirely on assessing the author's platform, marketing plan, and promotional capabilities.
"""
    elif proposal_type == 'no_marketing':
        evaluation_focus = """
This proposal does NOT include a Marketing section.
Score the Marketing category as 0.
Evaluate all other sections normally: Overview, Credentials, Comps, Writing, Outline, Completeness.
"""
    else:
        evaluation_focus = """
This is a FULL proposal submission. Evaluate all categories comprehensively.
"""

    prompt = f"""You are an expert literary agent evaluating book proposals for Write It Great LLC, an elite ghostwriting firm. 

{evaluation_focus}

Evaluate this proposal and provide scores and detailed feedback.

AUTHOR: {author_name}
BOOK TITLE: {book_title}

PROPOSAL TEXT:
{proposal_text[:50000]}  # Limit to ~50k chars to stay within token limits

---

Provide your evaluation as a JSON object with this exact structure:

{{
    "book_title": "{book_title}",
    "scores": {{
        "marketing": <0-100>,
        "overview": <0-100>,
        "credentials": <0-100>,
        "comps": <0-100>,
        "writing": <0-100>,
        "outline": <0-100>,
        "completeness": <0-100>
    }},
    "category_feedback": {{
        "marketing": {{
            "score": <0-100>,
            "strengths": ["strength 1", "strength 2", ...],
            "gaps": ["gap 1", "gap 2", ...],
            "summary": "2-3 sentence summary of this category"
        }},
        "overview": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }},
        "credentials": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }},
        "comps": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }},
        "writing": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }},
        "outline": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }},
        "completeness": {{
            "score": <0-100>,
            "strengths": [...],
            "gaps": [...],
            "summary": "..."
        }}
    }},
    "executive_summary": "3-5 sentences summarizing the overall proposal quality, key strengths, and main areas for improvement",
    "top_3_strengths": ["strength 1", "strength 2", "strength 3"],
    "top_3_improvements": ["improvement 1", "improvement 2", "improvement 3"],
    "recommended_next_steps": ["step 1", "step 2", "step 3"]
}}

SCORING GUIDELINES:
- 90-100: Exceptional, ready for top-tier publishers
- 80-89: Strong, minor improvements needed
- 70-79: Good foundation, some gaps to address
- 60-69: Promising but needs significant work
- 50-59: Weak, major revisions required
- Below 50: Not ready for submission

{"Note: Score Marketing as 0 since it was not included in this submission." if proposal_type == 'no_marketing' else ""}
{"Note: Score all non-Marketing categories as 0 since only Marketing was submitted." if proposal_type == 'marketing_only' else ""}

Return ONLY the JSON object, no other text.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are an expert literary agent and book proposal evaluator. Respond only with valid JSON."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        temperature=0.3,
        max_tokens=4000
    )
    
    # Parse the response
    response_text = response.choices[0].message.content.strip()
    
    # Clean up potential markdown formatting
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    
    evaluation = json.loads(response_text.strip())
    
    # Override scores based on proposal type
    if proposal_type == 'marketing_only':
        # Zero out non-marketing scores
        for category in ['overview', 'credentials', 'comps', 'writing', 'outline', 'completeness']:
            evaluation['scores'][category] = 0
            if category in evaluation.get('category_feedback', {}):
                evaluation['category_feedback'][category]['score'] = 0
                evaluation['category_feedback'][category]['summary'] = "Not submitted - Marketing only evaluation"
                evaluation['category_feedback'][category]['strengths'] = []
                evaluation['category_feedback'][category]['gaps'] = ["Not included in submission"]
                
    elif proposal_type == 'no_marketing':
        # Zero out marketing score
        evaluation['scores']['marketing'] = 0
        if 'marketing' in evaluation.get('category_feedback', {}):
            evaluation['category_feedback']['marketing']['score'] = 0
            evaluation['category_feedback']['marketing']['summary'] = "Not submitted - No marketing section included"
            evaluation['category_feedback']['marketing']['strengths'] = []
            evaluation['category_feedback']['marketing']['gaps'] = ["Marketing section not included in submission"]
    
    # Calculate weighted total score
    evaluation['total_score'] = calculate_weighted_score(evaluation['scores'], proposal_type)
    evaluation['tier'] = determine_tier(evaluation['total_score'])
    evaluation['proposal_type'] = proposal_type
    evaluation['weights_used'] = get_weights_for_type(proposal_type)
    
    return evaluation
