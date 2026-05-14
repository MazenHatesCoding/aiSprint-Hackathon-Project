# Keheilan AISprint — Agricultural Investment Platform

> Fractional farm investment platform with AI-powered risk scoring, yield forecasting, deal matching, and live investor–operator communication.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up your .env file
cp .env_template .env
# then open .env and paste your Groq API key

# 3. Run the server
uvicorn app:app --reload

# 4. Open in browser
http://localhost:8000
```

---

## Project Structure

```
aisprint/
├── app.py                  ← FastAPI backend — all API routes
├── database.py             ← SQLite layer — all DB operations
├── auth.py                 ← JWT auth (pure stdlib, no extra deps)
├── requirements.txt
├── .env                    ← GROQ_API_KEY + SECRET_KEY + DB_PATH
│
├── ai/
│   ├── risk_scorer.py      ← Farm risk rating (Approve/Review/Reject)
│   ├── yield_predictor.py  ← Crop yield + ROI forecast (live weather)
│   ├── deal_matcher.py     ← Matches investor to live DB farms
│   └── risk_calculator.py  ← Composite 5-category risk score (live weather)
│
└── frontend/
    ├── index.html          ← Public landing page
    ├── login.html
    ← register.html
    ├── investor.html       ← Investor dashboard
    ├── operator.html       ← Farm Operator dashboard
    └── admin.html          ← Admin dashboard
```

---

## Default Admin Account

| Field    | Value                  |
|----------|------------------------|
| Email    | admin@keheilan.com     |
| Password | admin123               |

> Change this password immediately in production.

---

## AI Provider

This project uses **Groq** (free tier) via the OpenAI-compatible SDK.

Get your free API key at: https://console.groq.com

```env
GROQ_API_KEY=your_key_here
```

Model in use: `llama-3.3-70b-versatile`

> Previously used Anthropic (`claude-sonnet-4-5`). Migrated to Groq to remove API cost dependency. All 4 AI modules are in `ai/` and follow the same pattern — swap `GROQ_MODEL` and `base_url` to use any OpenAI-compatible provider.

---

## User Roles

| Role     | What they can do |
|----------|-----------------|
| **Investor** | Browse farm listings, invest capital, view portfolio, receive operator requests, run AI yield/risk tools by Farm ID, use AI deal matcher against live farms |
| **Operator** | List farms, submit performance reports, run AI risk scorer, explore investors, send investment requests |
| **Admin**    | Approve/flag/close farms, manage users (activate/suspend), view platform stats |

---

## Investor Dashboard — Tabs

| Tab | Description |
|-----|-------------|
| Overview | Portfolio stats, total invested, expected returns, recent transactions |
| Browse Farms | All approved/active farm listings with Farm IDs, funding progress, invest button |
| My Portfolio | All personal investments with expected returns |
| Requests | Incoming offers from operators — includes Yield Predict and Calculate Risk shortcuts per farm, accept/decline actions |
| AI Deal Matcher | Matches investor profile against **live approved farms** from the database (not hardcoded) |
| Yield Predictor | Forecast crop yield + ROI — **prefill by Farm ID** or enter manually |
| Risk Calculator | 5-category composite risk score with live weather — **prefill by Farm ID** or enter manually |

---

## Operator Dashboard — Tabs

| Tab | Description |
|-----|-------------|
| Overview | Farm count, capital raised, pending reviews |
| My Farms | All listed farms with **Farm IDs** prominently displayed |
| List New Farm | Submit a new farm — Farm ID shown in success message |
| Explore Investors | Browse platform investors — 1 featured (hardcoded), rest dynamic from DB. Send direct requests. |
| Sent Requests | Track all outreach — shows Investor ID, Farm ID, message, and status |
| Reports | Submit seasonal performance reports per farm |
| AI Risk Scorer | Pre-check farm risk before listing — prefill from existing farm data |

---

## ID System

Every entity has a visible ID shown throughout the UI:

| Entity | Where it appears |
|--------|-----------------|
| **Farm ID** | Farm cards (Browse, My Farms), prefill inputs, report dropdowns, sent requests |
| **Investor ID** | Explore cards, sent requests log |
| **Operator ID** | Sidebar footer (operator dashboard) |

Investors can enter a Farm ID directly into the Yield Predictor or Risk Calculator to auto-populate all fields.

---

## Investor ↔ Operator Request Flow

```
Operator                              Investor
   │                                      │
   ├─ Explore Investors tab               │
   ├─ Clicks "Send Request" on investor   │
   ├─ Selects farm + writes message       │
   ├─ POST /api/requests ──────────────► DB
   │                                      │
   │                              ◄── Requests tab (badge shows unread count)
   │                              ◄── Card shows farm details, operator message
   │                              ◄── Buttons: Invest / Yield Predict / Calculate Risk / Decline
   │                                      │
   ◄── Sent Requests tab shows status ───┘
       (pending → seen → accepted/declined)
```

---

## AI Modules

| Module | Route | Used by | Notes |
|--------|-------|---------|-------|
| Farm Risk Scorer | `POST /api/risk-score` | Operator, Admin | Returns Approve/Review/Reject + score |
| Yield Predictor | `POST /api/yield-predict` | Investor | Pulls live 16-day weather from Open-Meteo |
| Deal Matcher | `POST /api/deal-match` | Investor | Queries **live DB farms** — no hardcoded data |
| Risk Calculator | `POST /api/risk-calculate` | Investor | 5-category weighted composite score + live weather |

### Farm ID Prefill Endpoints

```
GET /api/farms/{id}/prefill-yield   → pre-fills Yield Predictor form
GET /api/farms/{id}/prefill-risk    → pre-fills Risk Calculator form
```

---

## Full API Reference

### Auth
```
POST /api/auth/register     → { email, password, full_name, role }
POST /api/auth/login        → { email, password }
GET  /api/auth/me           → current user (requires Bearer token)
```

### Farms
```
POST  /api/farms                        → create farm (operator/admin)
GET   /api/farms                        → list farms (role-filtered)
GET   /api/farms/{id}                   → single farm
PATCH /api/farms/{id}/status            → update status (admin)
POST  /api/farms/{id}/score-risk        → score + save risk to farm
GET   /api/farms/{id}/prefill-yield     → yield form prefill data
GET   /api/farms/{id}/prefill-risk      → risk form prefill data
```

### Investments
```
POST /api/investments   → invest in a farm (investor)
GET  /api/investments   → list investments (role-filtered)
```

### Requests (Investor ↔ Operator)
```
POST  /api/requests                 → send request (operator)
GET   /api/requests                 → list requests (role-filtered: investor sees inbox, operator sees sent)
PATCH /api/requests/{id}/status     → update status: seen | accepted | declined
```

### Reports
```
POST /api/reports           → submit report (operator)
GET  /api/reports/{farm_id} → list reports for a farm
```

### Transactions
```
GET /api/transactions   → list transactions (role-filtered)
```

### Users & Admin
```
GET   /api/investors                    → list investors (operator/admin)
GET   /api/admin/stats                  → platform stats (admin)
GET   /api/admin/users                  → all users (admin)
PATCH /api/admin/users/{id}/active      → suspend/activate user (admin)
```

### AI
```
POST /api/risk-score        → farm risk rating
POST /api/yield-predict     → crop yield + ROI forecast
POST /api/deal-match        → investor ↔ live farm matching
POST /api/risk-calculate    → composite risk score
```

### System
```
GET /api/health   → { status: "ok" }
```

---

## Database Tables

| Table | Description |
|-------|-------------|
| `users` | All users (investors, operators, admins) |
| `farms` | Farm listings with status, risk score, funding progress |
| `investments` | Investor → Farm investment records |
| `transactions` | Financial transaction log |
| `performance_reports` | Operator-submitted seasonal reports |
| `investor_requests` | Operator → Investor outreach messages |

---

## Auth

All protected routes require:
```
Authorization: Bearer <JWT>
```

Token is stored in `localStorage` as `kh_token` after login/register.

Public routes (no auth needed):
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /` and all frontend pages

---
