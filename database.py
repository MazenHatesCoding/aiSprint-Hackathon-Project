import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "aisprint.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL UNIQUE,
            hashed_pw   TEXT    NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('investor','operator','admin')),
            full_name   TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            is_active   INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS farms (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id     INTEGER NOT NULL REFERENCES users(id),
            name            TEXT    NOT NULL,
            location        TEXT    NOT NULL,
            crop_type       TEXT    NOT NULL,
            size_feddan     REAL    NOT NULL,
            target_raise    REAL    NOT NULL,
            raised_so_far   REAL    NOT NULL DEFAULT 0,
            expected_roi    REAL    NOT NULL,
            duration_months INTEGER NOT NULL,
            description     TEXT,
            status          TEXT    NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending','approved','active','closed','flagged')),
            risk_score      INTEGER,
            risk_label      TEXT,
            risk_details    TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS investments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            investor_id     INTEGER NOT NULL REFERENCES users(id),
            farm_id         INTEGER NOT NULL REFERENCES farms(id),
            amount          REAL    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK(status IN ('active','completed','withdrawn')),
            invested_at     TEXT    NOT NULL DEFAULT (datetime('now')),
            expected_return REAL,
            actual_return   REAL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            farm_id     INTEGER REFERENCES farms(id),
            type        TEXT    NOT NULL CHECK(type IN ('deposit','withdrawal','return','investment')),
            amount      REAL    NOT NULL,
            note        TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS performance_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            farm_id     INTEGER NOT NULL REFERENCES farms(id),
            operator_id INTEGER NOT NULL REFERENCES users(id),
            period      TEXT    NOT NULL,
            yield_kg    REAL,
            revenue     REAL,
            expenses    REAL,
            notes       TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS investor_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL REFERENCES users(id),
            investor_id INTEGER NOT NULL REFERENCES users(id),
            farm_id     INTEGER NOT NULL REFERENCES farms(id),
            message     TEXT    NOT NULL DEFAULT '',
            status      TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','seen','accepted','declined')),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)

    from auth import hash_password
    cur.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (email, hashed_pw, role, full_name) VALUES (?,?,?,?)",
            ("admin@keheilan.com", hash_password("admin123"), "admin", "Platform Admin")
        )

    conn.commit()
    conn.close()


# ── Users ──────────────────────────────────────────────────────────────────

def create_user(email, hashed_pw, role, full_name):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (email, hashed_pw, role, full_name) VALUES (?,?,?,?)",
            (email, hashed_pw, role, full_name)
        )
        conn.commit()
        return get_user_by_id(cur.lastrowid)
    finally:
        conn.close()

def get_user_by_email(email):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_users():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def list_investors():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, full_name, email, created_at FROM users WHERE role='investor' AND is_active=1 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def set_user_active(user_id, active):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), user_id))
        conn.commit()
    finally:
        conn.close()


# ── Farms ──────────────────────────────────────────────────────────────────

def create_farm(operator_id, data):
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO farms
               (operator_id, name, location, crop_type, size_feddan,
                target_raise, expected_roi, duration_months, description)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (operator_id, data["name"], data["location"], data["crop_type"],
             data["size_feddan"], data["target_raise"], data["expected_roi"],
             data["duration_months"], data.get("description", ""))
        )
        conn.commit()
        return get_farm_by_id(cur.lastrowid)
    finally:
        conn.close()

def get_farm_by_id(farm_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT f.*, u.full_name as operator_name FROM farms f JOIN users u ON f.operator_id=u.id WHERE f.id=?",
            (farm_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_farms(status=None, operator_id=None):
    conn = get_db()
    try:
        q = """SELECT f.*, u.full_name as operator_name
               FROM farms f JOIN users u ON f.operator_id=u.id"""
        params, where = [], []
        if status:
            where.append("f.status=?")
            params.append(status)
        if operator_id:
            where.append("f.operator_id=?")
            params.append(operator_id)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY f.created_at DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def update_farm_status(farm_id, status):
    conn = get_db()
    try:
        conn.execute("UPDATE farms SET status=? WHERE id=?", (status, farm_id))
        conn.commit()
    finally:
        conn.close()

def update_farm_risk(farm_id, score, label, details):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE farms SET risk_score=?, risk_label=?, risk_details=? WHERE id=?",
            (score, label, details, farm_id)
        )
        conn.commit()
    finally:
        conn.close()


# ── Investments ────────────────────────────────────────────────────────────

def create_investment(investor_id, farm_id, amount):
    conn = get_db()
    try:
        farm = get_farm_by_id(farm_id)
        expected = round(amount * (1 + (farm["expected_roi"] / 100) * (farm["duration_months"] / 12)), 2)
        cur = conn.execute(
            "INSERT INTO investments (investor_id, farm_id, amount, expected_return) VALUES (?,?,?,?)",
            (investor_id, farm_id, amount, expected)
        )
        conn.execute("UPDATE farms SET raised_so_far = raised_so_far + ? WHERE id=?", (amount, farm_id))
        conn.execute(
            "INSERT INTO transactions (user_id, farm_id, type, amount, note) VALUES (?,?,?,?,?)",
            (investor_id, farm_id, "investment", amount, f"Investment in {farm['name']}")
        )
        conn.commit()
        return get_investment_by_id(cur.lastrowid)
    finally:
        conn.close()

def get_investment_by_id(inv_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM investments WHERE id=?", (inv_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_investments(investor_id=None, farm_id=None):
    conn = get_db()
    try:
        q = """SELECT i.*, f.name as farm_name, f.crop_type, f.location,
                      f.expected_roi, f.status as farm_status
               FROM investments i JOIN farms f ON i.farm_id=f.id"""
        params, where = [], []
        if investor_id:
            where.append("i.investor_id=?")
            params.append(investor_id)
        if farm_id:
            where.append("i.farm_id=?")
            params.append(farm_id)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY i.invested_at DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Transactions ───────────────────────────────────────────────────────────

def list_transactions(user_id=None):
    conn = get_db()
    try:
        q = "SELECT * FROM transactions"
        params = []
        if user_id:
            q += " WHERE user_id=?"
            params.append(user_id)
        q += " ORDER BY created_at DESC LIMIT 50"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Performance Reports ────────────────────────────────────────────────────

def create_report(farm_id, operator_id, data):
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO performance_reports
               (farm_id, operator_id, period, yield_kg, revenue, expenses, notes)
               VALUES (?,?,?,?,?,?,?)""",
            (farm_id, operator_id, data["period"], data.get("yield_kg"),
             data.get("revenue"), data.get("expenses"), data.get("notes", ""))
        )
        conn.commit()
        row = conn.execute("SELECT * FROM performance_reports WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def list_reports(farm_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM performance_reports WHERE farm_id=? ORDER BY created_at DESC",
            (farm_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Investor Requests ──────────────────────────────────────────────────────

def create_investor_request(operator_id, investor_id, farm_id, message):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO investor_requests (operator_id, investor_id, farm_id, message) VALUES (?,?,?,?)",
            (operator_id, investor_id, farm_id, message)
        )
        conn.commit()
        return get_request_by_id(cur.lastrowid)
    finally:
        conn.close()

def get_request_by_id(req_id):
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT r.*, 
                   f.name as farm_name, f.crop_type, f.location, f.size_feddan,
                   f.expected_roi, f.duration_months, f.description,
                   f.target_raise, f.raised_so_far,
                   op.full_name as operator_name,
                   inv.full_name as investor_name
            FROM investor_requests r
            JOIN farms f ON r.farm_id = f.id
            JOIN users op ON r.operator_id = op.id
            JOIN users inv ON r.investor_id = inv.id
            WHERE r.id=?
        """, (req_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_requests_for_investor(investor_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT r.*,
                   f.name as farm_name, f.crop_type, f.location, f.size_feddan,
                   f.expected_roi, f.duration_months, f.description,
                   f.target_raise, f.raised_so_far,
                   f.risk_score, f.risk_label,
                   op.full_name as operator_name
            FROM investor_requests r
            JOIN farms f ON r.farm_id = f.id
            JOIN users op ON r.operator_id = op.id
            WHERE r.investor_id=?
            ORDER BY r.created_at DESC
        """, (investor_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def list_requests_for_operator(operator_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT r.*,
                   f.name as farm_name, f.crop_type, f.location,
                   inv.full_name as investor_name, inv.email as investor_email
            FROM investor_requests r
            JOIN farms f ON r.farm_id = f.id
            JOIN users inv ON r.investor_id = inv.id
            WHERE r.operator_id=?
            ORDER BY r.created_at DESC
        """, (operator_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def update_request_status(req_id, status):
    conn = get_db()
    try:
        conn.execute("UPDATE investor_requests SET status=? WHERE id=?", (status, req_id))
        conn.commit()
    finally:
        conn.close()


# ── Platform stats (admin) ─────────────────────────────────────────────────

def platform_stats():
    conn = get_db()
    try:
        total_users    = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_farms    = conn.execute("SELECT COUNT(*) FROM farms").fetchone()[0]
        pending_farms  = conn.execute("SELECT COUNT(*) FROM farms WHERE status='pending'").fetchone()[0]
        total_invested = conn.execute("SELECT COALESCE(SUM(amount),0) FROM investments").fetchone()[0]
        active_inv     = conn.execute("SELECT COUNT(*) FROM investments WHERE status='active'").fetchone()[0]
        return {
            "total_users": total_users,
            "total_farms": total_farms,
            "pending_farms": pending_farms,
            "total_invested_usd": round(total_invested, 2),
            "active_investments": active_inv,
        }
    finally:
        conn.close()
