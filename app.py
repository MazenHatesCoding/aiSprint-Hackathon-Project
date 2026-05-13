import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

import database
import auth as auth_module
from auth import get_current_user, require_role

from ai.risk_scorer import score_farm_risk
from ai.yield_predictor import predict_yield
from ai.deal_matcher import match_deals
from ai.risk_calculator import calculate_risk

app = FastAPI(title="AISprint — Keheilan Agricultural Investment Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    database.init_db()


# ── Static frontend ───────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def root():
    return FileResponse("frontend/index.html")

@app.get("/login")
def login_page():
    return FileResponse("frontend/login.html")

@app.get("/register")
def register_page():
    return FileResponse("frontend/register.html")

@app.get("/investor")
def investor_page():
    return FileResponse("frontend/investor.html")

@app.get("/operator")
def operator_page():
    return FileResponse("frontend/operator.html")

@app.get("/admin")
def admin_page():
    return FileResponse("frontend/admin.html")


# ══════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
def api_register(req: RegisterRequest):
    if req.role not in ("investor", "operator"):
        raise HTTPException(400, "Role must be investor or operator")
    if database.get_user_by_email(req.email):
        raise HTTPException(400, "Email already registered")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    hashed = auth_module.hash_password(req.password)
    user = database.create_user(req.email, hashed, req.role, req.full_name)
    token = auth_module.create_token(user["id"], user["role"])
    return {"success": True, "token": token, "user": _safe_user(user)}


@app.post("/api/auth/login")
def api_login(req: LoginRequest):
    user = database.get_user_by_email(req.email)
    if not user or not auth_module.verify_password(req.password, user["hashed_pw"]):
        raise HTTPException(401, "Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(403, "Account suspended")
    token = auth_module.create_token(user["id"], user["role"])
    return {"success": True, "token": token, "user": _safe_user(user)}


@app.get("/api/auth/me")
def api_me(user: dict = Depends(get_current_user)):
    return {"success": True, "user": _safe_user(user)}


def _safe_user(u: dict) -> dict:
    return {k: v for k, v in u.items() if k != "hashed_pw"}


# ══════════════════════════════════════════════════════════════════════════
# FARM ROUTES
# ══════════════════════════════════════════════════════════════════════════

class FarmCreateRequest(BaseModel):
    name: str
    location: str
    crop_type: str
    size_feddan: float
    target_raise: float
    expected_roi: float
    duration_months: int
    description: Optional[str] = ""


@app.post("/api/farms")
def api_create_farm(req: FarmCreateRequest, user: dict = Depends(require_role("operator", "admin"))):
    farm = database.create_farm(user["id"], req.model_dump())
    return {"success": True, "data": farm}


@app.get("/api/farms")
def api_list_farms(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    if user["role"] == "investor":
        farms = database.list_farms(status="approved") + database.list_farms(status="active")
    elif user["role"] == "operator":
        farms = database.list_farms(operator_id=user["id"])
    else:
        farms = database.list_farms(status=status)
    return {"success": True, "data": farms}


@app.get("/api/farms/{farm_id}")
def api_get_farm(farm_id: int, user: dict = Depends(get_current_user)):
    farm = database.get_farm_by_id(farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    return {"success": True, "data": farm}


@app.patch("/api/farms/{farm_id}/status")
def api_update_farm_status(farm_id: int, body: dict, user: dict = Depends(require_role("admin"))):
    status = body.get("status")
    if status not in ("pending", "approved", "active", "closed", "flagged"):
        raise HTTPException(400, "Invalid status")
    database.update_farm_status(farm_id, status)
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════
# INVESTMENT ROUTES
# ══════════════════════════════════════════════════════════════════════════

class InvestRequest(BaseModel):
    farm_id: int
    amount: float


@app.post("/api/investments")
def api_invest(req: InvestRequest, user: dict = Depends(require_role("investor"))):
    farm = database.get_farm_by_id(req.farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    if farm["status"] not in ("approved", "active"):
        raise HTTPException(400, "Farm is not open for investment")
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    inv = database.create_investment(user["id"], req.farm_id, req.amount)
    return {"success": True, "data": inv}


@app.get("/api/investments")
def api_list_investments(user: dict = Depends(get_current_user)):
    if user["role"] == "investor":
        data = database.list_investments(investor_id=user["id"])
    elif user["role"] == "admin":
        data = database.list_investments()
    else:
        data = []
    return {"success": True, "data": data}


# ══════════════════════════════════════════════════════════════════════════
# PERFORMANCE REPORT ROUTES
# ══════════════════════════════════════════════════════════════════════════

class ReportRequest(BaseModel):
    farm_id: int
    period: str
    yield_kg: Optional[float] = None
    revenue: Optional[float] = None
    expenses: Optional[float] = None
    notes: Optional[str] = ""


@app.post("/api/reports")
def api_create_report(req: ReportRequest, user: dict = Depends(require_role("operator"))):
    farm = database.get_farm_by_id(req.farm_id)
    if not farm or farm["operator_id"] != user["id"]:
        raise HTTPException(403, "Not your farm")
    report = database.create_report(req.farm_id, user["id"], req.model_dump())
    return {"success": True, "data": report}


@app.get("/api/reports/{farm_id}")
def api_list_reports(farm_id: int, user: dict = Depends(get_current_user)):
    return {"success": True, "data": database.list_reports(farm_id)}


# ══════════════════════════════════════════════════════════════════════════
# TRANSACTION ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/transactions")
def api_list_transactions(user: dict = Depends(get_current_user)):
    if user["role"] == "admin":
        data = database.list_transactions()
    else:
        data = database.list_transactions(user_id=user["id"])
    return {"success": True, "data": data}


# ══════════════════════════════════════════════════════════════════════════
# INVESTOR REQUESTS ROUTES
# ══════════════════════════════════════════════════════════════════════════

class InvestorRequestCreate(BaseModel):
    investor_id: int
    farm_id: int
    message: Optional[str] = ""


@app.post("/api/requests")
def api_create_request(req: InvestorRequestCreate, user: dict = Depends(require_role("operator"))):
    farm = database.get_farm_by_id(req.farm_id)
    if not farm or farm["operator_id"] != user["id"]:
        raise HTTPException(403, "Not your farm")
    investor = database.get_user_by_id(req.investor_id)
    if not investor or investor["role"] != "investor":
        raise HTTPException(404, "Investor not found")
    result = database.create_investor_request(user["id"], req.investor_id, req.farm_id, req.message)
    return {"success": True, "data": result}


@app.get("/api/requests")
def api_list_requests(user: dict = Depends(get_current_user)):
    if user["role"] == "investor":
        data = database.list_requests_for_investor(user["id"])
    elif user["role"] == "operator":
        data = database.list_requests_for_operator(user["id"])
    else:
        data = []
    return {"success": True, "data": data}


@app.patch("/api/requests/{req_id}/status")
def api_update_request_status(req_id: int, body: dict, user: dict = Depends(get_current_user)):
    status = body.get("status")
    if status not in ("seen", "accepted", "declined"):
        raise HTTPException(400, "Invalid status")
    database.update_request_status(req_id, status)
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════
# INVESTORS DIRECTORY (for operator explore tab)
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/investors")
def api_list_investors(user: dict = Depends(require_role("operator", "admin"))):
    investors = database.list_investors()
    return {"success": True, "data": investors}


# ══════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/stats")
def api_admin_stats(user: dict = Depends(require_role("admin"))):
    return {"success": True, "data": database.platform_stats()}


@app.get("/api/admin/users")
def api_admin_users(user: dict = Depends(require_role("admin"))):
    users = [_safe_user(u) for u in database.list_users()]
    return {"success": True, "data": users}


@app.patch("/api/admin/users/{uid}/active")
def api_toggle_user(uid: int, body: dict, user: dict = Depends(require_role("admin"))):
    database.set_user_active(uid, body.get("active", True))
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════
# AI ROUTES
# ══════════════════════════════════════════════════════════════════════════

class FarmRiskRequest(BaseModel):
    farm_name: str
    location: str
    crop_type: str
    farm_size_hectares: float
    years_in_operation: int
    annual_revenue_usd: float
    irrigation: bool
    soil_quality: str
    previous_defaults: bool
    certifications: List[str] = []

class YieldPredictRequest(BaseModel):
    farm_name: str
    crop_type: str
    farm_size_hectares: float
    latitude: float
    longitude: float
    soil_quality: str
    irrigation: bool
    planting_season: str
    investment_model: str
    investment_amount_usd: float

class DealMatchRequest(BaseModel):
    name: str
    investment_budget_usd: float
    risk_tolerance: str
    preferred_horizon_years: int
    preferred_model: str
    return_target_pct: float
    priorities: List[str] = []

class RiskCalcRequest(BaseModel):
    farm_name: str
    crop_type: str
    farm_size_hectares: float
    latitude: float
    longitude: float
    years_in_operation: int
    irrigation: bool
    soil_quality: str
    annual_revenue_usd: float
    debt_ratio: float
    previous_defaults: bool
    investment_model: str
    investment_amount_usd: float


@app.post("/api/risk-score")
def api_risk_score(req: FarmRiskRequest):
    try:
        return {"success": True, "data": score_farm_risk(req.model_dump())}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/yield-predict")
def api_yield_predict(req: YieldPredictRequest):
    try:
        return {"success": True, "data": predict_yield(req.model_dump())}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/deal-match")
def api_deal_match(req: DealMatchRequest, user: dict = Depends(get_current_user)):
    try:
        # Pull live approved/active farms from DB
        farms = database.list_farms(status="approved") + database.list_farms(status="active")
        return {"success": True, "data": match_deals(req.model_dump(), farms)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/risk-calculate")
def api_risk_calculate(req: RiskCalcRequest):
    try:
        return {"success": True, "data": calculate_risk(req.model_dump())}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── AI: prefill from farm ID ──────────────────────────────────────────────

@app.get("/api/farms/{farm_id}/prefill-yield")
def api_prefill_yield(farm_id: int, user: dict = Depends(get_current_user)):
    """Returns a YieldPredictRequest-compatible payload from a farm's DB data."""
    farm = database.get_farm_by_id(farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    # Map feddan → hectares (1 feddan ≈ 0.42 hectares)
    size_ha = round(farm["size_feddan"] * 0.42, 2)
    return {"success": True, "data": {
        "farm_name": farm["name"],
        "crop_type": farm["crop_type"],
        "farm_size_hectares": size_ha,
        "latitude": 30.0,
        "longitude": 31.0,
        "soil_quality": "good",
        "irrigation": True,
        "planting_season": "Winter",
        "investment_model": "farm_operations",
        "investment_amount_usd": 10000,
        "farm_id": farm["id"],
        "location": farm["location"],
        "expected_roi": farm["expected_roi"],
        "duration_months": farm["duration_months"],
    }}


@app.get("/api/farms/{farm_id}/prefill-risk")
def api_prefill_risk(farm_id: int, user: dict = Depends(get_current_user)):
    """Returns a RiskCalcRequest-compatible payload from a farm's DB data."""
    farm = database.get_farm_by_id(farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    size_ha = round(farm["size_feddan"] * 0.42, 2)
    return {"success": True, "data": {
        "farm_name": farm["name"],
        "crop_type": farm["crop_type"],
        "farm_size_hectares": size_ha,
        "latitude": 30.0,
        "longitude": 31.0,
        "years_in_operation": 3,
        "irrigation": True,
        "soil_quality": "good",
        "annual_revenue_usd": farm["target_raise"] * (farm["expected_roi"] / 100),
        "debt_ratio": 0.3,
        "previous_defaults": False,
        "investment_model": "farm_operations",
        "investment_amount_usd": 10000,
        "farm_id": farm["id"],
        "location": farm["location"],
    }}


# ── AI: save risk score to farm ───────────────────────────────────────────

class FarmRiskScoreRequest(BaseModel):
    farm_id: int
    farm_name: str
    location: str
    crop_type: str
    farm_size_hectares: float
    years_in_operation: int
    annual_revenue_usd: float
    irrigation: bool
    soil_quality: str
    previous_defaults: bool
    certifications: List[str] = []


@app.post("/api/farms/{farm_id}/score-risk")
def api_score_and_save(farm_id: int, req: FarmRiskScoreRequest,
                        user: dict = Depends(require_role("operator", "admin"))):
    farm = database.get_farm_by_id(farm_id)
    if not farm:
        raise HTTPException(404, "Farm not found")
    payload = req.model_dump()
    payload.pop("farm_id")
    result = score_farm_risk(payload)
    database.update_farm_risk(farm_id, result["risk_score"], result["risk_rating"],
                               str(result.get("summary", "")))
    return {"success": True, "data": result}


@app.get("/api/health")
def health():
    return {"status": "ok", "platform": "AISprint — Keheilan Asset Management"}
