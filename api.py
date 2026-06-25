"""
ESGrow API — FastAPI backend + Jinja2 server-side rendering
Database-backed. Run: uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
import os

import csv
from contextlib import asynccontextmanager

from database import SessionLocal, init_db
from models import Company, Sector, Score, IndicatorScore, IndicatorDefinition, ScoreHistory, FetchLog
import engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ── Indicator definitions (name + weight) ─────────────────
INDICATOR_DEFS = {
    "E01": ("Carbon Emissions Intensity", 0.20),
    "E02": ("Renewable Energy Usage", 0.18),
    "E03": ("Water Stewardship", 0.15),
    "E04": ("Waste Management & Circularity", 0.14),
    "E05": ("Biodiversity & Land Use", 0.13),
    "E06": ("Environmental Compliance", 0.12),
    "E07": ("Green Products / Services", 0.05),
    "E08": ("Climate Risk Disclosure", 0.03),
    "S01": ("Workforce Health & Safety", 0.22),
    "S02": ("Diversity & Inclusion", 0.18),
    "S03": ("Labour Standards", 0.14),
    "S04": ("Employee Development", 0.14),
    "S05": ("Community Investment", 0.12),
    "S06": ("Customer Welfare", 0.10),
    "S07": ("Supply Chain Standards", 0.06),
    "S08": ("Human Rights", 0.04),
    "G01": ("Board Independence", 0.22),
    "G02": ("Audit & Risk Oversight", 0.18),
    "G03": ("Executive Compensation", 0.17),
    "G04": ("Shareholder Rights", 0.14),
    "G05": ("Ethics & Anti-Corruption", 0.13),
    "G06": ("Regulatory Compliance", 0.08),
    "G07": ("ESG Integration in Strategy", 0.05),
    "G08": ("Transparency & Reporting", 0.03),
}

SECTOR_WEIGHTS = {
    "Mining":         {"E": 0.50, "S": 0.30, "G": 0.20},
    "Banking":        {"E": 0.15, "S": 0.35, "G": 0.50},
    "Energy":         {"E": 0.42, "S": 0.33, "G": 0.25},
    "Agriculture":    {"E": 0.42, "S": 0.33, "G": 0.25},
    "Telecoms":       {"E": 0.15, "S": 0.40, "G": 0.45},
    "Consumer Goods": {"E": 0.22, "S": 0.38, "G": 0.40},
    "Manufacturing":  {"E": 0.45, "S": 0.30, "G": 0.25},
}


def auto_seed():
    """If the database is empty, seed it from data/seed_all.csv."""
    db = SessionLocal()
    try:
        if db.query(Company).count() > 0:
            return

        csv_path = os.path.join(BASE_DIR, "data", "seed_all.csv")
        if not os.path.exists(csv_path):
            print("[auto_seed] No seed_all.csv found, skipping.")
            return

        print("[auto_seed] Empty database detected — seeding from CSV...")

        # 1. Seed sectors
        for name, weights in SECTOR_WEIGHTS.items():
            if not db.query(Sector).filter_by(name=name).first():
                db.add(Sector(name=name, weight_e=weights["E"],
                              weight_s=weights["S"], weight_g=weights["G"]))
        db.commit()

        # 2. Seed indicator definitions
        for ind_id, (ind_name, weight) in INDICATOR_DEFS.items():
            if not db.query(IndicatorDefinition).filter_by(id=ind_id).first():
                db.add(IndicatorDefinition(
                    id=ind_id, pillar=ind_id[0], name=ind_name,
                    weight=weight, sort_order=int(ind_id[1:]),
                ))
        db.commit()

        # 3. Import companies + indicator scores from CSV
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row["code"].strip()
                sector = db.query(Sector).filter_by(name=row["sector"].strip()).first()
                if not sector:
                    continue

                company = Company(
                    name=code,
                    display_name=row["display_name"].strip(),
                    sector_id=sector.id,
                    is_active=True,
                )
                db.add(company)
                db.flush()

                ind_ids = ([f"E{i:02d}" for i in range(1, 9)]
                           + [f"S{i:02d}" for i in range(1, 9)]
                           + [f"G{i:02d}" for i in range(1, 9)])
                for ind_id in ind_ids:
                    val = row.get(ind_id, "").strip()
                    if val:
                        db.add(IndicatorScore(
                            company_id=company.id,
                            indicator_id=ind_id,
                            score=float(val),
                            source=row.get("report_source", ""),
                        ))
        db.commit()

        # 4. Calculate scores
        engine.run_scoring(db)
        print(f"[auto_seed] Done — {db.query(Company).count()} companies loaded.")

    finally:
        db.close()


def run_migrations():
    """Add new columns to existing tables (safe to run multiple times)."""
    from sqlalchemy import text
    from database import engine as db_engine
    migrations = [
        "ALTER TABLE indicator_scores ADD COLUMN report_year INTEGER",
        "ALTER TABLE indicator_scores ADD COLUMN updated_at TIMESTAMP",
    ]
    with db_engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app):
    init_db()
    run_migrations()
    auto_seed()
    yield


# Ensure tables exist on startup (also called in lifespan, but kept for local dev)
init_db()

app = FastAPI(title="ESGrow API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── DB session dependency ───────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Helpers ─────────────────────────────────────────────────

def make_short_name(name):
    """Generate a short ticker-style name from company name."""
    SHORT_MAP = {
        "Standard Chartered Zambia": "SCB",
        "Zambian Breweries": "ZBL",
        "Copperbelt Energy Corporation": "CEC",
        "First National Bank Zambia Limited": "FNB",
        "Zanaco Bank": "ZANACO",
        "Stanbic Bank Zambia Limited": "STANBIC",
        "Shoprite Holdings Limited (Zambia operations)": "SHOPRITE",
        "Absa Bank Zambia PLC": "ABSA",
        "Airtel Zambia": "AIRTEL",
        "MTN Zambia": "MTN",
        "Prima Reinsurance Plc (now Zambia Reinsurance Plc)": "PRIMA",
        "Zambia Sugar": "ZAMSUG",
        "Zambeef Products PLC": "ZAMBEEF",
        "ZCCM Investments Holdings": "ZCCM",
        "First Quantum Minerals": "FQM",
        "Lafarge Zambia": "LAFARGE",
        "Access Bank Zambia Limited": "ACCESS",
        "Puma Energy Zambia Plc": "PUMA",
        "Unitrans Zambia (KAP Limited division)": "UNITRANS",
        "National Breweries Plc": "NATBREW",
    }
    return SHORT_MAP.get(name, name.split()[0].upper()[:6])


def make_company_id(name):
    """Generate a stable ID from company name."""
    ID_MAP = {
        "Standard Chartered Zambia": "SCB_ZAMBIA",
        "Zambian Breweries": "ZBL",
        "Copperbelt Energy Corporation": "CEC",
        "First National Bank Zambia Limited": "FNB",
        "Zanaco Bank": "ZANACO",
        "Stanbic Bank Zambia Limited": "STANBIC",
        "Shoprite Holdings Limited (Zambia operations)": "SHOPRITE",
        "Absa Bank Zambia PLC": "ABSA",
        "Airtel Zambia": "AIRTEL",
        "MTN Zambia": "MTN_ZAMBIA",
        "Prima Reinsurance Plc (now Zambia Reinsurance Plc)": "PRIMA",
        "Zambia Sugar": "ZAMSUG",
        "Zambeef Products PLC": "ZAMBEEF",
        "ZCCM Investments Holdings": "ZCCM",
        "First Quantum Minerals": "FQM",
        "Lafarge Zambia": "LAFARGE",
        "Access Bank Zambia Limited": "ACCESS",
        "Puma Energy Zambia Plc": "PUMA",
        "Unitrans Zambia (KAP Limited division)": "UNITRANS",
        "National Breweries Plc": "NATBREW",
    }
    return ID_MAP.get(name, name.upper().replace(" ", "_"))


def format_score(score_row):
    """Convert a Score ORM object into the API dict shape."""
    name = score_row.company.display_name or score_row.company.name
    return {
        "id": make_company_id(name),
        "name": name,
        "short": make_short_name(name),
        "Company": name,
        "Sector": score_row.company.sector.name,
        "sector": score_row.company.sector.name,
        "E": score_row.e_score,
        "S": score_row.s_score,
        "G": score_row.g_score,
        "Final": score_row.final_score,
        "Band": score_row.band,
    }


def load_leaderboard(db: Session):
    """Query all scores, sorted by final_score descending."""
    rows = (
        db.query(Score)
        .join(Company)
        .join(Sector)
        .filter(Company.is_active == True)
        .order_by(Score.final_score.desc())
        .all()
    )
    return [format_score(r) for r in rows]


# ── HTML page (server-side rendered) ────────────────────────

def build_company_context(request: Request, name: str, db: Session) -> dict:
    """Query all data for a single company detail page."""
    company = (
        db.query(Company)
        .filter(Company.name.ilike(name))
        .filter(Company.is_active == True)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{name}' not found.")

    score = company.score
    if not score:
        raise HTTPException(status_code=404, detail=f"No scores calculated for '{name}'.")

    # Build indicators grouped by pillar, ordered by sort_order
    indicators: dict = {"E": [], "S": [], "G": []}
    for iscore in sorted(company.indicator_scores, key=lambda x: x.indicator.sort_order):
        pillar = iscore.indicator.pillar
        indicators[pillar].append({
            "id": iscore.indicator_id,
            "name": iscore.indicator.name,
            "score": iscore.score,
        })

    # Determine rank among all active companies
    all_scores = (
        db.query(Score)
        .join(Company)
        .filter(Company.is_active == True)
        .order_by(Score.final_score.desc())
        .all()
    )
    rank = next((i + 1 for i, s in enumerate(all_scores) if s.company_id == company.id), 0)
    total = len(all_scores)

    return {
        "request": request,
        "company_name": company.name,
        "display_name": company.display_name or company.name,
        "sector_name": company.sector.name,
        "band": score.band,
        "final_score": score.final_score,
        "e_score": score.e_score,
        "s_score": score.s_score,
        "g_score": score.g_score,
        "rank": rank,
        "total_companies": total,
        "indicators": indicators,
    }


def build_template_context(request: Request, db: Session) -> dict:
    """Compute every piece of data the template needs — no hardcoded values in HTML."""
    data = load_leaderboard(db)
    scores = [c["Final"] for c in data]
    sectors = sorted(set(c["Sector"] for c in data))
    bands = {}
    for c in data:
        bands[c["Band"]] = bands.get(c["Band"], 0) + 1

    top = data[0] if data else {}

    return {
        "request": request,
        "leaderboard": data,
        "top": top,
        "total_companies": len(data),
        "total_sectors": len(sectors),
        "sectors": sectors,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "highest_score": max(scores) if scores else 0,
        "lowest_score": min(scores) if scores else 0,
        "bands": bands,
        "leader_count": bands.get("ESG Leader", 0),
        "performer_count": bands.get("ESG Performer", 0),
        "developing_count": bands.get("Developing", 0),
        "indicator_count": 24,
        "pillar_count": 3,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serve the new React-based ESGrow frontend."""
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.get("/legacy", response_class=HTMLResponse)
def legacy_dashboard(request: Request, db: Session = Depends(get_db)):
    """Legacy server-rendered landing page (kept for reference)."""
    ctx = build_template_context(request, db)
    return templates.TemplateResponse(name="index.html", request=request, context=ctx)


@app.get("/company/{name}", response_class=HTMLResponse)
def company_detail(name: str, request: Request, db: Session = Depends(get_db)):
    """Render the company detail page with all 24 indicator scores."""
    ctx = build_company_context(request, name, db)
    return templates.TemplateResponse(name="company.html", request=request, context=ctx)


# ── JSON API endpoints ──────────────────────────────────────

@app.get("/api/scores")
def get_all_scores(db: Session = Depends(get_db)):
    return load_leaderboard(db)


@app.get("/api/scores/{company}")
def get_company_score(company: str, db: Session = Depends(get_db)):
    row = (
        db.query(Score)
        .join(Company)
        .filter(Company.name.ilike(company))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Company '{company}' not found.")
    return format_score(row)


@app.get("/api/sectors")
def get_sectors(db: Session = Depends(get_db)):
    sectors = (
        db.query(Sector.name)
        .join(Company)
        .filter(Company.is_active == True)
        .distinct()
        .order_by(Sector.name)
        .all()
    )
    return {"sectors": [s[0] for s in sectors]}


@app.get("/api/scores/sector/{sector}")
def get_by_sector(sector: str, db: Session = Depends(get_db)):
    rows = (
        db.query(Score)
        .join(Company)
        .join(Sector)
        .filter(Sector.name.ilike(sector))
        .filter(Company.is_active == True)
        .order_by(Score.final_score.desc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No companies found for sector '{sector}'.")
    return [format_score(r) for r in rows]


@app.get("/api/company/{name}/indicators")
def get_company_indicators(name: str, db: Session = Depends(get_db)):
    """Return all 24 indicator scores for a company, grouped by pillar."""
    company = (
        db.query(Company)
        .filter(Company.name.ilike(name))
        .filter(Company.is_active == True)
        .first()
    )
    if not company:
        # Also try matching display_name
        company = (
            db.query(Company)
            .filter(Company.is_active == True)
            .all()
        )
        company = next((c for c in company if make_company_id(c.display_name or c.name) == name), None)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{name}' not found.")

    indicators = {"E": [], "S": [], "G": []}
    for iscore in sorted(company.indicator_scores, key=lambda x: x.indicator.sort_order):
        pillar = iscore.indicator.pillar
        indicators[pillar].append({
            "id": iscore.indicator_id,
            "name": iscore.indicator.name,
            "score": iscore.score,
        })
    return indicators


@app.get("/api/dashboard")
def get_dashboard_data(db: Session = Depends(get_db)):
    """Return everything the React frontend needs in a single call."""
    # Companies with scores
    rows = (
        db.query(Score)
        .join(Company)
        .join(Sector)
        .filter(Company.is_active == True)
        .order_by(Score.final_score.desc())
        .all()
    )
    companies = [format_score(r) for r in rows]

    # Sectors with weights
    sectors_db = db.query(Sector).all()
    sector_list = sorted(set(c["sector"] for c in companies))
    sector_weights = {}
    for s in sectors_db:
        sector_weights[s.name] = {"E": s.weight_e, "S": s.weight_s, "G": s.weight_g}

    # All indicators grouped by company ID
    all_indicators = {}
    for row in rows:
        company = row.company
        cid = make_company_id(company.display_name or company.name)
        indicators = {"E": [], "S": [], "G": []}
        for iscore in sorted(company.indicator_scores, key=lambda x: x.indicator.sort_order):
            pillar = iscore.indicator.pillar
            indicators[pillar].append({
                "id": iscore.indicator_id,
                "name": iscore.indicator.name,
                "score": iscore.score,
            })
        all_indicators[cid] = indicators

    return {
        "companies": companies,
        "sectors": sector_list,
        "sectorWeights": sector_weights,
        "indicators": all_indicators,
    }


@app.post("/api/refresh")
def refresh_scores(db: Session = Depends(get_db), quick: bool = True):
    """Refresh ESG scores. Use ?quick=false to run full pipeline (scrape + AI score)."""
    if quick:
        results = engine.run_scoring(db, notes="Manual refresh")
        engine.export_json(results)
        return {"status": "ok", "message": "Scores recalculated successfully."}
    else:
        import pipeline
        summary = pipeline.run_pipeline(db, quick=False)
        return {"status": "ok", "summary": summary}


@app.get("/api/company/{name}/history")
def get_company_history(name: str, db: Session = Depends(get_db)):
    """Return score history for a company — used for trend charts."""
    company = (
        db.query(Company)
        .filter(Company.name.ilike(name))
        .filter(Company.is_active == True)
        .first()
    )
    if not company:
        company = next(
            (c for c in db.query(Company).filter(Company.is_active == True).all()
             if (c.display_name or c.name).lower() == name.lower()
             or make_company_id(c.display_name or c.name) == name),
            None,
        )
    if not company:
        raise HTTPException(status_code=404, detail=f"Company '{name}' not found.")

    history = (
        db.query(ScoreHistory)
        .filter_by(company_id=company.id)
        .order_by(ScoreHistory.report_year.asc(), ScoreHistory.calculated_at.asc())
        .all()
    )

    return {
        "company": company.display_name or company.name,
        "code": company.name,
        "history": [
            {
                "report_year": h.report_year,
                "e_score": h.e_score,
                "s_score": h.s_score,
                "g_score": h.g_score,
                "final_score": h.final_score,
                "band": h.band,
                "calculated_at": h.calculated_at.isoformat() if h.calculated_at else None,
                "notes": h.notes,
            }
            for h in history
        ],
    }


@app.get("/api/pipeline/status")
def get_pipeline_status(db: Session = Depends(get_db)):
    """Return the status of the data pipeline — latest fetch per company."""
    from sqlalchemy import func

    latest_fetch = (
        db.query(FetchLog)
        .order_by(FetchLog.fetched_at.desc())
        .first()
    )

    companies = (
        db.query(
            Company.name,
            func.max(FetchLog.fetched_at).label("last_fetched"),
            FetchLog.status,
        )
        .outerjoin(FetchLog, Company.id == FetchLog.company_id)
        .filter(Company.is_active == True)
        .group_by(Company.name, FetchLog.status)
        .all()
    )

    return {
        "last_run": latest_fetch.fetched_at.isoformat() if latest_fetch else None,
        "companies": [
            {
                "code": c.name,
                "last_fetched": c.last_fetched.isoformat() if c.last_fetched else None,
                "status": c.status or "never_fetched",
            }
            for c in companies
        ],
    }


@app.get("/api/summary")
def get_summary(db: Session = Depends(get_db)):
    data = load_leaderboard(db)
    scores = [c["Final"] for c in data]
    bands = {}
    for c in data:
        bands[c["Band"]] = bands.get(c["Band"], 0) + 1
    return {
        "total_companies": len(data),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "highest": max(scores) if scores else 0,
        "lowest": min(scores) if scores else 0,
        "bands": bands,
    }


# Static files — serve fonts, logo, and other assets from /static/
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_assets")
