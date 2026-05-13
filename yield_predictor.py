from openai import OpenAI
import os
import json
import urllib.request

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

GROQ_MODEL = "llama-3.3-70b-versatile"


def get_weather_data(latitude: float, longitude: float) -> dict:
    """Fetch real climate data from Open-Meteo (free, no API key needed)."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        f"&forecast_days=16"
        f"&timezone=auto"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read().decode())
        daily = data.get("daily", {})
        temps_max = daily.get("temperature_2m_max", [])
        temps_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        wind = daily.get("windspeed_10m_max", [])

        def safe_avg(lst):
            clean = [x for x in lst if x is not None]
            return round(sum(clean) / len(clean), 2) if clean else None

        return {
            "avg_max_temp_c": safe_avg(temps_max),
            "avg_min_temp_c": safe_avg(temps_min),
            "total_precipitation_mm": round(sum(x for x in precip if x is not None), 2),
            "avg_wind_speed_kmh": safe_avg(wind),
            "forecast_days": len(temps_max),
            "source": "Open-Meteo 16-day forecast",
        }
    except Exception as e:
        return {"error": str(e), "source": "Open-Meteo unavailable"}


def predict_yield(farm_data: dict) -> dict:
    """
    Forecasts expected crop yield and return range using farm data + real weather.

    farm_data keys:
        - farm_name: str
        - crop_type: str
        - farm_size_hectares: float
        - latitude: float
        - longitude: float
        - soil_quality: str (poor/average/good/excellent)
        - irrigation: bool
        - planting_season: str (e.g. "Spring", "Winter")
        - investment_model: str (fractional_land / farm_operations / hybrid)
        - investment_amount_usd: float
    """
    weather = get_weather_data(
        farm_data.get("latitude", 30.0), farm_data.get("longitude", 31.0)
    )

    prompt = f"""You are an agricultural yield analyst for a fractional farming investment platform.

Using the farm profile and current weather forecast data below, predict the crop yield and estimate the investor return range.

Farm Profile:
{json.dumps(farm_data, indent=2)}

Current 16-Day Weather Forecast (real data):
{json.dumps(weather, indent=2)}

Provide your forecast in this exact JSON format:
{{
  "yield_estimate_tons_per_hectare": {{
    "low": <float>,
    "expected": <float>,
    "high": <float>
  }},
  "total_yield_estimate_tons": {{
    "low": <float>,
    "expected": <float>,
    "high": <float>
  }},
  "estimated_return_usd": {{
    "low": <float>,
    "expected": <float>,
    "high": <float>
  }},
  "roi_percentage": {{
    "low": <float>,
    "expected": <float>,
    "high": <float>
  }},
  "confidence_level": "Low" | "Medium" | "High",
  "weather_impact": "Favorable" | "Neutral" | "Unfavorable",
  "weather_notes": "<1-2 sentences on how current weather affects this crop>",
  "key_factors": ["<factor 1>", "<factor 2>", ...],
  "harvest_window": "<estimated timeframe e.g. '3-4 months'>"
}}

Use real agronomic benchmarks for the crop type. Factor in the weather data meaningfully.
Return only valid JSON, no additional text."""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
    result["weather_data_used"] = weather
    return result
