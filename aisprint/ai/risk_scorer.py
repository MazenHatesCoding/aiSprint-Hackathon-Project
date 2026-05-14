from openai import OpenAI
import os
import json

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

GROQ_MODEL = "llama-3.3-70b-versatile"


def score_farm_risk(farm_data: dict) -> dict:
    """
    Analyzes a farm profile and returns a risk rating with detailed reasoning.

    farm_data keys:
        - farm_name: str
        - location: str
        - crop_type: str
        - farm_size_hectares: float
        - years_in_operation: int
        - annual_revenue_usd: float
        - irrigation: bool
        - soil_quality: str (poor/average/good/excellent)
        - previous_defaults: bool
        - certifications: list[str]
    """

    prompt = f"""You are an agricultural investment risk analyst for a fractional farming investment platform.

Analyze the following farm profile and provide a structured risk assessment:

Farm Profile:
{json.dumps(farm_data, indent=2)}

Provide your assessment in this exact JSON format:
{{
  "risk_rating": "Low" | "Medium" | "High",
  "risk_score": <integer 0-100, where 0 = no risk, 100 = maximum risk>,
  "summary": "<2-3 sentence executive summary>",
  "strengths": ["<strength 1>", "<strength 2>", ...],
  "concerns": ["<concern 1>", "<concern 2>", ...],
  "recommendation": "Approve" | "Review" | "Reject",
  "recommendation_reasoning": "<1-2 sentences explaining the recommendation>"
}}

Base your analysis on:
- Farm size and operational history
- Crop type volatility and market demand
- Infrastructure (irrigation, soil quality)
- Financial track record
- Certifications and compliance signals
- Geographic and climate exposure implied by location

Return only valid JSON, no additional text."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)
