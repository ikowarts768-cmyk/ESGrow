"""
ESGrow AI Scorer
Uses Claude API to extract ESG indicator scores from annual report text.

Each company gets scored on 24 indicators (E01-E08, S01-S08, G01-G08).
Claude reads the extracted text and assigns a score (0-100) for each indicator,
along with a brief justification.

Usage:
  from ai_scorer import score_report
  result = score_report(text, "Standard Chartered Zambia", "Banking")
"""

import json
import os
import time

# Indicator definitions — what each code means (same as api.py)
INDICATOR_DEFS = {
    "E01": "Carbon Emissions Intensity",
    "E02": "Renewable Energy Usage",
    "E03": "Water Stewardship",
    "E04": "Waste Management & Circularity",
    "E05": "Biodiversity & Land Use",
    "E06": "Environmental Compliance",
    "E07": "Green Products / Services",
    "E08": "Climate Risk Disclosure",
    "S01": "Workforce Health & Safety",
    "S02": "Diversity & Inclusion",
    "S03": "Labour Standards",
    "S04": "Employee Development",
    "S05": "Community Investment",
    "S06": "Customer Welfare",
    "S07": "Supply Chain Standards",
    "S08": "Human Rights",
    "G01": "Board Independence",
    "G02": "Audit & Risk Oversight",
    "G03": "Executive Compensation",
    "G04": "Shareholder Rights",
    "G05": "Ethics & Anti-Corruption",
    "G06": "Regulatory Compliance",
    "G07": "ESG Integration in Strategy",
    "G08": "Transparency & Reporting",
}

# The prompt tells Claude exactly what to do
SCORING_PROMPT = """You are an ESG (Environmental, Social, Governance) analyst scoring a Zambian company.

## Company
Name: {company_name}
Sector: {sector}

## Task
Read the annual report text below and score the company on each of the 24 ESG indicators listed.
For each indicator, assign a score from 0 to 100:
- 80-100: Strong disclosure and performance (specific data, targets, progress)
- 60-79: Good disclosure (some data, policies in place)
- 40-59: Basic disclosure (mentions the topic but lacks detail)
- 20-39: Minimal disclosure (vague references only)
- 0-19: No disclosure found for this indicator

## ESG Indicators to Score
{indicators_list}

## Important Rules
1. Base scores ONLY on evidence in the text — don't assume or guess
2. If an indicator topic is not mentioned at all, score it 20 or below
3. Higher scores require specific data (numbers, percentages, targets)
4. Return VALID JSON only — no other text before or after the JSON

## Required JSON Format
{{
  "scores": {{
    "E01": {{"score": 72, "justification": "Reports Scope 1 emissions of 5,792 tCO2e with 96% reduction target"}},
    "E02": {{"score": 85, "justification": "RE100 member with 95% renewable energy usage"}},
    ... (all 24 indicators)
  }}
}}

## Annual Report Text
{report_text}
"""


def build_indicators_list():
    """Format the indicator definitions for the prompt."""
    lines = []
    for code in sorted(INDICATOR_DEFS.keys()):
        name = INDICATOR_DEFS[code]
        pillar = {"E": "Environmental", "S": "Social", "G": "Governance"}[code[0]]
        lines.append(f"- {code}: {name} ({pillar})")
    return "\n".join(lines)


def score_report(text, company_name, sector, max_retries=2):
    """
    Send report text to Claude and get back 24 indicator scores.

    Returns:
      {
        "scores": {"E01": 72, "E02": 85, ...},
        "justifications": {"E01": "Reports Scope 1...", ...},
        "model": "claude-sonnet-4-20250514",
        "success": True
      }
    """
    try:
        import anthropic
    except ImportError:
        print("[ERROR] anthropic package not installed. Run: pip install anthropic")
        return {"scores": {}, "justifications": {}, "success": False}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set in environment variables.")
        return {"scores": {}, "justifications": {}, "success": False}

    client = anthropic.Anthropic(api_key=api_key)

    prompt = SCORING_PROMPT.format(
        company_name=company_name,
        sector=sector,
        indicators_list=build_indicators_list(),
        report_text=text[:80000],  # Stay within context limits
    )

    for attempt in range(max_retries):
        try:
            print(f"  Sending to Claude API (attempt {attempt + 1})...")

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Parse the JSON from Claude's response
            # Sometimes Claude wraps it in markdown code blocks
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())

            # Extract scores and justifications
            scores = {}
            justifications = {}

            for code, info in data.get("scores", {}).items():
                if code in INDICATOR_DEFS:
                    score_val = info.get("score", 0)
                    # Validate score is between 0 and 100
                    score_val = max(0, min(100, int(score_val)))
                    scores[code] = score_val
                    justifications[code] = info.get("justification", "")

            # Check we got all 24 indicators
            missing = set(INDICATOR_DEFS.keys()) - set(scores.keys())
            if missing:
                print(f"  [WARN] Missing indicators: {missing}")
                for code in missing:
                    scores[code] = 30  # Default for missing indicators
                    justifications[code] = "Not scored by AI — indicator not found in report"

            print(f"  [OK] Scored {len(scores)} indicators for {company_name}")

            return {
                "scores": scores,
                "justifications": justifications,
                "model": "claude-sonnet-4-20250514",
                "success": True,
            }

        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

        except Exception as e:
            print(f"  [WARN] API error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    print(f"  [ERROR] Failed to score {company_name} after {max_retries} attempts")
    return {"scores": {}, "justifications": {}, "success": False}


if __name__ == "__main__":
    # Quick test with sample text
    sample_text = """
    Annual Report 2024 - Test Company
    Our carbon emissions were 5,000 tCO2e this year, down 15% from last year.
    We use 60% renewable energy across our operations.
    Board is 45% independent with 3 of 7 directors being non-executive.
    """

    result = score_report(sample_text, "Test Company", "Banking")
    if result["success"]:
        print("\nScores:")
        for code in sorted(result["scores"]):
            print(f"  {code}: {result['scores'][code]} — {result['justifications'].get(code, '')}")
    else:
        print("\nScoring failed. Check API key and try again.")
