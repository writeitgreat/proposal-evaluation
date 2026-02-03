#!/usr/bin/env python3
"""
Book Proposal Evaluation Engine - Comprehensive Version
Uses OpenAI to evaluate book proposals with detailed analysis, red flags, and actionable feedback.
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
    'comps': 0.10,          # 10%
    'writing': 0.15,        # 15%
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
    'overview': 0.29,
    'credentials': 0.21,
    'comps': 0.14,
    'writing': 0.21,
    'outline': 0.07,
    'completeness': 0.08
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
    else:
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


def get_tier_description(tier):
    """Get description for tier."""
    descriptions = {
        'A': 'Exceptional - Your proposal demonstrates strong potential for top-tier publishers.',
        'B': 'Strong Foundation - With targeted improvements, your proposal could reach A-tier status.',
        'C': 'Developing - Your proposal shows promise but needs significant strengthening in key areas.',
        'D': 'Early Stage - Your proposal needs substantial work before submission to publishers.'
    }
    return descriptions.get(tier, '')


def evaluate_proposal(proposal_text, proposal_type, author_name, book_title):
    """
    Evaluate a book proposal using OpenAI with comprehensive analysis.
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
Evaluate all other sections normally.
"""
    else:
        evaluation_focus = """
This is a FULL proposal submission. Evaluate all categories comprehensively.
"""

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
{proposal_text[:80000]}

---

Provide your evaluation as a JSON object with this EXACT structure:

{{
    "title": "{book_title}",
    "author": "{author_name}",
    "overallScore": <calculated weighted score 0-100>,
    "tier": "<A, B, C, or D>",
    "executiveSummary": "<3-5 sentence executive summary of the proposal's strengths and areas for improvement>",
    
    "redFlags": [
        "<list any critical issues like: no_platform, weak_credentials, oversaturated_market, poor_writing_quality, incomplete_proposal, unrealistic_claims, no_clear_audience, derivative_concept>"
    ],
    
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
            "currentState": "<2-3 sentences describing current state of this section>",
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
                "improvementExample": "<quote a passage that could be improved and explain how>"
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
        "reasoning": "<2-3 sentences explaining the estimate based on platform, market, and comparable titles>"
    }},
    
    "recommendedNextSteps": ["<step 1>", "<step 2>", "<step 3>"]
}}

SCORING GUIDELINES:
- 90-100: Exceptional, ready for top-tier publishers
- 80-89: Strong, minor improvements needed  
- 70-79: Good foundation, some gaps to address
- 60-69: Promising but needs significant work
- 50-59: Weak, major revisions required
- Below 50: Not ready for submission

RED FLAG RULES:
- If "no_platform" is detected, cap Marketing score at 40
- If "poor_writing_quality" is detected, cap Writing score at 50
- If "incomplete_proposal" is detected, cap Completeness at 40

{"Note: Score Marketing as 0 since it was not included." if proposal_type == 'no_marketing' else ""}
{"Note: Score all non-Marketing categories as 0." if proposal_type == 'marketing_only' else ""}

Return ONLY the JSON object, no other text.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        max_tokens=6000
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
        for category in ['overview', 'credentials', 'comps', 'writing', 'outline', 'completeness']:
            if 'scores' in evaluation and category in evaluation['scores']:
                evaluation['scores'][category]['score'] = 0
            if 'detailedAnalysis' in evaluation and category in evaluation['detailedAnalysis']:
                evaluation['detailedAnalysis'][category] = {
                    'currentState': 'Not submitted - Marketing only evaluation',
                    'strengths': 'N/A',
                    'gaps': 'Not included in submission',
                    'exampleOfExcellence': 'N/A',
                    'actionItems': []
                }
                
    elif proposal_type == 'no_marketing':
        if 'scores' in evaluation and 'marketing' in evaluation['scores']:
            evaluation['scores']['marketing']['score'] = 0
        if 'detailedAnalysis' in evaluation and 'marketing' in evaluation['detailedAnalysis']:
            evaluation['detailedAnalysis']['marketing'] = {
                'currentState': 'Not submitted - No marketing section included',
                'strengths': 'N/A',
                'gaps': 'Marketing section not included',
                'exampleOfExcellence': 'N/A',
                'actionItems': ['Consider adding a marketing section to strengthen your proposal']
            }
    
    # Calculate weighted total score from individual scores
    scores_dict = {}
    if 'scores' in evaluation:
        for cat, data in evaluation['scores'].items():
            if isinstance(data, dict):
                scores_dict[cat] = data.get('score', 0)
            else:
                scores_dict[cat] = data
    
    evaluation['total_score'] = calculate_weighted_score(scores_dict, proposal_type)
    evaluation['tier'] = determine_tier(evaluation['total_score'])
    evaluation['tierDescription'] = get_tier_description(evaluation['tier'])
    evaluation['proposal_type'] = proposal_type
    evaluation['weights_used'] = get_weights_for_type(proposal_type)
    
    # Ensure backwards compatibility with old field names
    if 'overallScore' not in evaluation:
        evaluation['overallScore'] = evaluation['total_score']
    if 'executive_summary' not in evaluation and 'executiveSummary' in evaluation:
        evaluation['executive_summary'] = evaluation['executiveSummary']
    if 'top_3_strengths' not in evaluation and 'strengths' in evaluation:
        evaluation['top_3_strengths'] = evaluation['strengths'][:3]
    if 'top_3_improvements' not in evaluation and 'improvements' in evaluation:
        evaluation['top_3_improvements'] = evaluation['improvements'][:3]
    if 'recommended_next_steps' not in evaluation and 'recommendedNextSteps' in evaluation:
        evaluation['recommended_next_steps'] = evaluation['recommendedNextSteps']
    
    return evaluation
