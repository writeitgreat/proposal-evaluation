#!/usr/bin/env python3
"""
Book Proposal Evaluation Engine - Comprehensive Version
Uses OpenAI to evaluate book proposals with detailed analysis.
"""

import os
import json
import re
import fitz  # PyMuPDF
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
    'marketing': 1.00,
    'overview': 0.00,
    'credentials': 0.00,
    'comps': 0.00,
    'writing': 0.00,
    'outline': 0.00,
    'completeness': 0.00
}

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
        if isinstance(score, dict):
            score = score.get('score', 0)
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


def clean_json_response(response_text):
    """Clean and extract JSON from the response."""
    text = response_text.strip()
    
    # Remove markdown code blocks
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Find JSON object boundaries
    start = text.find('{')
    end = text.rfind('}')
    
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    
    return text


def evaluate_proposal(proposal_text, proposal_type, author_name, book_title):
    """
    Evaluate a book proposal using OpenAI with comprehensive analysis.
    """
    
    # Determine evaluation focus based on proposal type
    if proposal_type == 'marketing_only':
        evaluation_focus = "You are evaluating ONLY the Marketing & Platform section. Score all other categories as 0."
    elif proposal_type == 'no_marketing':
        evaluation_focus = "This proposal does NOT include a Marketing section. Score Marketing as 0."
    else:
        evaluation_focus = "This is a FULL proposal submission. Evaluate all categories."

    system_prompt = """You are an elite literary agent with 25+ years of experience evaluating book proposals. Your evaluations are thorough, actionable, and honest. Always respond with valid JSON only - no markdown, no explanations, just the JSON object."""

    user_prompt = f"""{evaluation_focus}

Evaluate this book proposal and return a JSON object.

AUTHOR: {author_name}
BOOK TITLE: {book_title}

PROPOSAL TEXT:
{proposal_text[:60000]}

---

Return ONLY a valid JSON object with this structure (no markdown, no code blocks, just JSON):

{{
    "executiveSummary": "3-5 sentence summary of the proposal quality, strengths, and areas for improvement",
    "redFlags": ["list any critical issues like no_platform, weak_credentials, poor_writing_quality, or empty array if none"],
    "scores": {{
        "marketing": {{"score": 0-100, "weight": 30}},
        "overview": {{"score": 0-100, "weight": 20}},
        "credentials": {{"score": 0-100, "weight": 15}},
        "comps": {{"score": 0-100, "weight": 10}},
        "writing": {{"score": 0-100, "weight": 15}},
        "outline": {{"score": 0-100, "weight": 5}},
        "completeness": {{"score": 0-100, "weight": 5}}
    }},
    "detailedAnalysis": {{
        "marketing": {{
            "currentState": "2-3 sentences about current state",
            "strengths": "what is working well",
            "gaps": "what is missing or weak",
            "exampleOfExcellence": "what A-tier looks like for this category",
            "actionItems": ["action 1", "action 2", "action 3"]
        }},
        "overview": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"]
        }},
        "credentials": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"]
        }},
        "comps": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"]
        }},
        "writing": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"],
            "writingExamples": {{
                "strongPassage": "quote a strong passage from the proposal",
                "improvementExample": "quote a passage that could be improved and explain how"
            }}
        }},
        "outline": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"]
        }},
        "completeness": {{
            "currentState": "2-3 sentences",
            "strengths": "strengths",
            "gaps": "gaps",
            "exampleOfExcellence": "example",
            "actionItems": ["action 1", "action 2"]
        }}
    }},
    "strengths": ["top strength 1", "top strength 2", "top strength 3"],
    "improvements": ["top improvement 1", "top improvement 2", "top improvement 3"],
    "priorityActionPlan": [
        {{"priority": 1, "action": "most important action", "timeline": "This week", "impact": "why this matters"}},
        {{"priority": 2, "action": "second action", "timeline": "Next 2 weeks", "impact": "why this matters"}},
        {{"priority": 3, "action": "third action", "timeline": "Next month", "impact": "why this matters"}}
    ],
    "pathToATier": "2-3 sentences describing the specific path to reach A-tier status",
    "advanceEstimate": {{
        "viable": true or false,
        "lowRange": number or 0,
        "highRange": number or 0,
        "confidence": "Low or Medium or High",
        "reasoning": "2-3 sentences explaining the estimate"
    }},
    "recommendedNextSteps": ["step 1", "step 2", "step 3"]
}}

SCORING: 90-100 exceptional, 80-89 strong, 70-79 good, 60-69 promising, 50-59 weak, below 50 not ready.

Return ONLY the JSON object, nothing else."""

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
    response_text = response.choices[0].message.content
    
    # Clean and parse JSON
    cleaned_json = clean_json_response(response_text)
    
    try:
        evaluation = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        print(f"Response text: {response_text[:500]}...")
        raise ValueError(f"Failed to parse evaluation response: {str(e)}")
    
    # Extract scores for weighted calculation
    scores_dict = {}
    if 'scores' in evaluation:
        for cat, data in evaluation['scores'].items():
            if isinstance(data, dict):
                scores_dict[cat] = data.get('score', 0)
            else:
                scores_dict[cat] = data
    
    # Override scores based on proposal type
    if proposal_type == 'marketing_only':
        for category in ['overview', 'credentials', 'comps', 'writing', 'outline', 'completeness']:
            scores_dict[category] = 0
            if 'scores' in evaluation and category in evaluation['scores']:
                if isinstance(evaluation['scores'][category], dict):
                    evaluation['scores'][category]['score'] = 0
                else:
                    evaluation['scores'][category] = 0
                    
    elif proposal_type == 'no_marketing':
        scores_dict['marketing'] = 0
        if 'scores' in evaluation and 'marketing' in evaluation['scores']:
            if isinstance(evaluation['scores']['marketing'], dict):
                evaluation['scores']['marketing']['score'] = 0
            else:
                evaluation['scores']['marketing'] = 0
    
    # Calculate final score and tier
    evaluation['total_score'] = calculate_weighted_score(scores_dict, proposal_type)
    evaluation['tier'] = determine_tier(evaluation['total_score'])
    evaluation['tierDescription'] = get_tier_description(evaluation['tier'])
    evaluation['proposal_type'] = proposal_type
    evaluation['weights_used'] = get_weights_for_type(proposal_type)
    
    # Backwards compatibility
    evaluation['overallScore'] = evaluation['total_score']
    if 'executiveSummary' in evaluation:
        evaluation['executive_summary'] = evaluation['executiveSummary']
    if 'strengths' in evaluation:
        evaluation['top_3_strengths'] = evaluation['strengths'][:3]
    if 'improvements' in evaluation:
        evaluation['top_3_improvements'] = evaluation['improvements'][:3]
    if 'recommendedNextSteps' in evaluation:
        evaluation['recommended_next_steps'] = evaluation['recommendedNextSteps']
    
    return evaluation
