from openai import OpenAI
import os
import json

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

GROQ_MODEL = "llama-3.3-70b-versatile"


def match_deals(investor_profile: dict, farms: list) -> dict:
    """
    Matches an investor to the best farm deals from the live database.
    farms: list of farm dicts (approved/active) from database.
    """

    if not farms:
        return {
            "top_matches": [],
            "not_recommended": [],
            "advisor_note": "No farms are currently available for investment. Check back soon.",
            "available_deals": []
        }

    deal_list = []
    for f in farms:
        deal_list.append({
            "deal_id": f"FARM-{f['id']}",
            "farm_id": f["id"],
            "farm_name": f["name"],
            "location": f["location"],
            "crop_type": f["crop_type"],
            "farm_size_feddan": f["size_feddan"],
            "target_raise_usd": f["target_raise"],
            "raised_so_far_usd": f["raised_so_far"],
            "projected_annual_return_pct": f["expected_roi"],
            "investment_horizon_months": f["duration_months"],
            "risk_rating": f.get("risk_label") or "Unrated",
            "description": f.get("description") or "",
            "operator": f.get("operator_name") or "Unknown",
            "status": f["status"],
        })

    prompt = f"""You are an investment advisor on a fractional agricultural investment platform.

An investor has provided their profile. Match them to the best farm deals from the available listings, ranked by fit.

Investor Profile:
{json.dumps(investor_profile, indent=2)}

Available Farm Deals (live from platform database):
{json.dumps(deal_list, indent=2)}

Provide your matches in this exact JSON format:
{{
  "top_matches": [
    {{
      "deal_id": "<id e.g. FARM-3>",
      "farm_name": "<name>",
      "match_score": <integer 0-100>,
      "match_label": "Excellent" | "Good" | "Fair",
      "why_this_fits": "<2-3 sentences explaining why this deal fits this investor specifically>",
      "trade_offs": "<1 sentence on what they give up with this choice>"
    }}
  ],
  "not_recommended": [
    {{
      "deal_id": "<id>",
      "reason": "<1 sentence>"
    }}
  ],
  "advisor_note": "<2-3 sentence personalized portfolio advice for this investor>"
}}

Rank top_matches from best to worst fit. Include ALL deals split between top_matches and not_recommended.
Return only valid JSON, no additional text."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    result["available_deals"] = deal_list
    return result
