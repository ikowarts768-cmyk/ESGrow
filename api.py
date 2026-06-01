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

from database import SessionLocal, init_db
from models import Company, Sector, Score
import engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Ensure tables exist on startup
init_db()

app = FastAPI(title="ESGrow API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
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

def format_score(score_row):
    """Convert a Score ORM object into the API dict shape."""
    return {
        "Company": score_row.company.name,
        "Sector": score_row.company.sector.name,
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


@app.post("/api/refresh")
def refresh_scores(db: Session = Depends(get_db)):
    results = engine.run_scoring(db)
    engine.export_json(results)
    return {"status": "ok", "message": "Scores refreshed successfully."}


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
