from openai import OpenAI
import os
import json
import urllib.request

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

GROQ_MODEL = "llama-3.3-70b-versatile"


def get_weather_risk_data(latitude: float, longitude: float) -> dict:
    """Fetch weather data and compute risk-relevant signals from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        f"windspeed_10m_max,et0_fao_evapotranspiration"
        f"&forecast_days=16&timezone=auto"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode())

        daily = data.get("daily", {})
        temps_max = [x for x in daily.get("temperature_2m_max", []) if x is not None]
        temps_min = [x for x in daily.get("temperature_2m_min", []) if x is not None]
        precip = [x for x in daily.get("precipitation_sum", []) if x is not None]
        wind = [x for x in daily.get("windspeed_10m_max", []) if x is not None]
        et0 = [x for x in daily.get("et0_fao_evapotranspiration", []) if x is not None]

        total_precip = sum(precip)
        avg_max_temp = sum(temps_max) / len(temps_max) if temps_max else None
        max_wind = max(wind) if wind else None
        avg_et0 = sum(et0) / len(et0) if et0 else None

        drought_risk = (
            "High" if total_precip < 5 and (avg_et0 or 0) > 4
            else "Medium" if total_precip < 20
            else "Low"
        )
        heat_stress = (
            "High" if avg_max_temp and avg_max_temp > 38
            else "Medium" if avg_max_temp and avg_max_temp > 32
            else "Low"
        )
        wind_risk = (
            "High" if max_wind and max_wind > 60
            else "Medium" if max_wind and max_wind > 40
            else "Low"
        )
        flood_risk = (
            "High" if total_precip > 80
            else "Medium" if total_precip > 40
            else "Low"
        )

        return {
            "avg_max_temp_c": round(avg_max_temp, 1) if avg_max_temp else None,
            "avg_min_temp_c": round(sum(temps_min) / len(temps_min), 1) if temps_min else None,
            "total_precipitation_mm_16d": round(total_precip, 1),
            "max_wind_speed_kmh": round(max_wind, 1) if max_wind else None,
            "avg_evapotranspiration_mm": round(avg_et0, 2) if avg_et0 else None,
            "computed_risks": {
                "drought_risk": drought_risk,
                "heat_stress_risk": heat_stress,
                "wind_damage_risk": wind_risk,
                "flood_risk": flood_risk,
            },
            "source": "Open-Meteo 16-day forecast",
        }
    except Exception as e:
        return {"error": str(e), "source": "Open-Meteo unavailable"}


def calculate_risk(farm_data: dict) -> dict:
    """
    Produces a composite risk score with a category-by-category breakdown.

    farm_data keys:
        - farm_name: str
        - crop_type: str
        - farm_size_hectares: float
        - latitude: float
        - longitude: float
        - years_in_operation: int
        - irrigation: bool
        - soil_quality: str
        - annual_revenue_usd: float
        - debt_ratio: float (0.0 - 1.0)
        - previous_defaults: bool
        - investment_model: str
        - investment_amount_usd: float
    """

    weather_risk = get_weather_risk_data(
        farm_data.get("latitude", 30.0),
        farm_data.get("longitude", 31.0),
    )

    prompt = f"""You are a quantitative risk analyst for an agricultural investment platform.

Calculate a comprehensive composite risk score for this farm investment opportunity.

Farm & Investment Data:
{json.dumps(farm_data, indent=2)}

Real-Time Weather Risk Data (16-day forecast):
{json.dumps(weather_risk, indent=2)}

Provide your risk calculation in this exact JSON format:
{{
  "composite_risk_score": <integer 0-100, where 0=no risk, 100=maximum risk>,
  "composite_risk_label": "Very Low" | "Low" | "Medium" | "High" | "Very High",
  "category_scores": {{
    "climate_weather_risk": {{
      "score": <0-100>,
      "label": "Low" | "Medium" | "High",
      "notes": "<1 sentence>"
    }},
    "operational_risk": {{
      "score": <0-100>,
      "label": "Low" | "Medium" | "High",
      "notes": "<1 sentence>"
    }},
    "financial_risk": {{
      "score": <0-100>,
      "label": "Low" | "Medium" | "High",
      "notes": "<1 sentence>"
    }},
    "market_risk": {{
      "score": <0-100>,
      "label": "Low" | "Medium" | "High",
      "notes": "<1 sentence>"
    }},
    "infrastructure_risk": {{
      "score": <0-100>,
      "label": "Low" | "Medium" | "High",
      "notes": "<1 sentence>"
    }}
  }},
  "top_risk_factors": ["<factor 1>", "<factor 2>", "<factor 3>"],
  "mitigating_factors": ["<factor 1>", "<factor 2>"],
  "investor_guidance": "<2-3 sentences advising the investor on how to interpret this score>"
}}

Weight climate/weather risk at 25%, operational at 25%, financial at 20%, market at 15%, infrastructure at 15%.
Return only valid JSON, no additional text."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    result["weather_data_used"] = weather_risk
    return result
