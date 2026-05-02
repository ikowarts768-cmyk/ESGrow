"""
ESGrow Migration — Import Excel data into database.
Run once: python migrate.py
"""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import inspect

from database import init_db, get_session, engine
from models import (
    Sector, Company, IndicatorDefinition, IndicatorScore, Score, ScoreHistory
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "data", "ESGrow_Zambia_Complete_v1.0.xlsx")
OUTPUT_JSON = os.path.join(BASE_DIR, "data", "output.json")


# ── Reference data ──────────────────────────────────────────

SECTOR_WEIGHTS = {
    "Mining":         {"E": 0.50, "S": 0.30, "G": 0.20},
    "Banking":        {"E": 0.15, "S": 0.35, "G": 0.50},
    "Energy":         {"E": 0.42, "S": 0.33, "G": 0.25},
    "Agriculture":    {"E": 0.42, "S": 0.33, "G": 0.25},
    "Telecoms":       {"E": 0.15, "S": 0.40, "G": 0.45},
    "Consumer Goods": {"E": 0.22, "S": 0.38, "G": 0.40},
    "Manufacturing":  {"E": 0.45, "S": 0.30, "G": 0.25},
}

E_WEIGHTS = {
    "E01": 0.20, "E02": 0.18, "E03": 0.15, "E04": 0.14,
    "E05": 0.13, "E06": 0.12, "E07": 0.05, "E08": 0.03,
}
S_WEIGHTS = {
    "S01": 0.22, "S02": 0.18, "S03": 0.14, "S04": 0.14,
    "S05": 0.12, "S06": 0.10, "S07": 0.06, "S08": 0.04,
}
G_WEIGHTS = {
    "G01": 0.22, "G02": 0.18, "G03": 0.17, "G04": 0.14,
    "G05": 0.13, "G06": 0.08, "G07": 0.05, "G08": 0.03,
}

COMPANIES = [
    ("SCB_ZAMBIA",  "Banking",        "Standard Chartered Zambia"),
    ("CEC",         "Energy",         "Copperbelt Energy Corporation"),
    ("ZBL",         "Consumer Goods", "Zambian Breweries"),
    ("ZANACO",      "Banking",        "Zanaco Bank"),
    ("AIRTEL",      "Telecoms",       "Airtel Zambia"),
    ("ZAMSUG",      "Agriculture",    "Zambia Sugar"),
    ("FQM",         "Mining",         "First Quantum Minerals"),
    ("ZCCM",        "Mining",         "ZCCM Investments Holdings"),
    ("LAFARGE",     "Manufacturing",  "Lafarge Zambia"),
    ("MTN_ZAMBIA",  "Telecoms",       "MTN Zambia"),
]


def get_band(score):
    if score >= 80: return "ESG Leader"
    if score >= 60: return "ESG Performer"
    if score >= 40: return "Developing"
    if score >= 20: return "Laggard"
    return "Critical Risk"


def calculate_pillar_score(indicators, weights):
    score = 0
    total_weight = 0
    for key, weight in weights.items():
        if key in indicators and indicators[key] is not None:
            score += indicators[key] * weight
            total_weight += weight
    return score / total_weight if total_weight > 0 else 0


# ── Migration steps ─────────────────────────────────────────

def seed_sectors(session):
    print("\n[1/5] Seeding sectors...")
    for name, weights in SECTOR_WEIGHTS.items():
        existing = session.query(Sector).filter_by(name=name).first()
        if not existing:
            session.add(Sector(
                name=name,
                weight_e=weights["E"],
                weight_s=weights["S"],
                weight_g=weights["G"],
            ))
    session.commit()
    count = session.query(Sector).count()
    print(f"  {count} sectors in database.")


def seed_indicator_definitions(session):
    print("\n[2/5] Seeding indicator definitions...")

    # Read indicator names from one representative sheet
    df = pd.read_excel(EXCEL_PATH, sheet_name="SCB_ZAMBIA", header=4)
    df.columns = df.columns.str.strip().str.replace('\u2013', '-').str.replace('\u2014', '-')

    indicator_names = {}
    for _, row in df.iterrows():
        ind_id = str(row.iloc[0]).strip()
        if len(ind_id) == 3 and ind_id[0] in ("E", "S", "G") and ind_id[1:].isdigit():
            indicator_names[ind_id] = str(row.iloc[1]).strip()

    all_weights = {**E_WEIGHTS, **S_WEIGHTS, **G_WEIGHTS}

    for ind_id, weight in all_weights.items():
        existing = session.query(IndicatorDefinition).filter_by(id=ind_id).first()
        if not existing:
            pillar = ind_id[0]
            sort_order = int(ind_id[1:])
            name = indicator_names.get(ind_id, f"Indicator {ind_id}")
            session.add(IndicatorDefinition(
                id=ind_id,
                pillar=pillar,
                name=name,
                weight=weight,
                sort_order=sort_order,
            ))
    session.commit()
    count = session.query(IndicatorDefinition).count()
    print(f"  {count} indicator definitions in database.")


def seed_companies(session):
    print("\n[3/5] Seeding companies...")
    for name, sector_name, display_name in COMPANIES:
        existing = session.query(Company).filter_by(name=name).first()
        if not existing:
            sector = session.query(Sector).filter_by(name=sector_name).first()
            session.add(Company(
                name=name,
                display_name=display_name,
                sector_id=sector.id,
            ))
    session.commit()
    count = session.query(Company).count()
    print(f"  {count} companies in database.")


def import_indicator_scores(session):
    print("\n[4/5] Importing indicator scores from Excel...")

    for comp_name, sector_name, _ in COMPANIES:
        company = session.query(Company).filter_by(name=comp_name).first()

        df = pd.read_excel(EXCEL_PATH, sheet_name=comp_name, header=4)
        df.columns = df.columns.str.strip().str.replace('\u2013', '-').str.replace('\u2014', '-')

        # Find score column
        score_col = None
        for col in df.columns:
            if str(col).startswith("Score"):
                score_col = col
                break

        if score_col is None:
            print(f"  WARNING: No score column in sheet '{comp_name}', skipping.")
            continue

        count = 0
        for _, row in df.iterrows():
            ind_id = str(row.iloc[0]).strip()
            if not (len(ind_id) == 3 and ind_id[0] in ("E", "S", "G") and ind_id[1:].isdigit()):
                continue

            raw_score = row[score_col]
            if pd.isna(raw_score):
                continue

            # Parse the numeric score from "85 — description" format
            score_str = str(raw_score).strip()
            try:
                numeric = float(score_str.split()[0].split("\u2014")[0].split("-")[0])
                if not (0 <= numeric <= 100):
                    continue
            except (ValueError, IndexError):
                continue

            # Extract other fields
            raw_value = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else None
            unit = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else None
            source = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else None

            # Check for existing
            existing = session.query(IndicatorScore).filter_by(
                company_id=company.id, indicator_id=ind_id
            ).first()

            if not existing:
                session.add(IndicatorScore(
                    company_id=company.id,
                    indicator_id=ind_id,
                    score=numeric,
                    raw_value=raw_value,
                    unit=unit,
                    source=source,
                ))
                count += 1

        session.commit()
        print(f"  {comp_name}: {count} indicator scores imported.")


def calculate_and_store_scores(session):
    print("\n[5/5] Calculating and storing scores...")

    now = datetime.now(timezone.utc)
    companies = session.query(Company).filter_by(is_active=True).all()

    results = []
    for company in companies:
        sector = company.sector

        # Load indicator scores into dict
        indicators = {}
        for iscore in company.indicator_scores:
            indicators[iscore.indicator_id] = iscore.score

        # Calculate pillar scores
        e_score = calculate_pillar_score(indicators, E_WEIGHTS)
        s_score = calculate_pillar_score(indicators, S_WEIGHTS)
        g_score = calculate_pillar_score(indicators, G_WEIGHTS)

        # Final weighted score
        final = (
            e_score * sector.weight_e +
            s_score * sector.weight_s +
            g_score * sector.weight_g
        )
        band = get_band(final)

        e_r = round(e_score, 1)
        s_r = round(s_score, 1)
        g_r = round(g_score, 1)
        f_r = round(final, 1)

        # Upsert current score
        existing = session.query(Score).filter_by(company_id=company.id).first()
        if existing:
            existing.e_score = e_r
            existing.s_score = s_r
            existing.g_score = g_r
            existing.final_score = f_r
            existing.band = band
            existing.calculated_at = now
        else:
            session.add(Score(
                company_id=company.id,
                e_score=e_r, s_score=s_r, g_score=g_r,
                final_score=f_r, band=band, calculated_at=now,
            ))

        # Append to history
        session.add(ScoreHistory(
            company_id=company.id,
            e_score=e_r, s_score=s_r, g_score=g_r,
            final_score=f_r, band=band, calculated_at=now,
            report_year=2024,
            notes="Initial migration from Excel v1.0",
        ))

        results.append({
            "Company": company.name,
            "Sector": sector.name,
            "E": e_r, "S": s_r, "G": g_r,
            "Final": f_r, "Band": band,
        })

        print(f"  {company.name}: E={e_r} S={s_r} G={g_r} Final={f_r} ({band})")

    session.commit()
    results.sort(key=lambda x: x["Final"], reverse=True)
    return results


def verify_against_json(db_results):
    print("\n[Verification] Comparing DB scores against output.json...")

    with open(OUTPUT_JSON) as f:
        original = json.load(f)

    original_map = {c["Company"]: c for c in original}
    db_map = {c["Company"]: c for c in db_results}

    all_match = True
    for name, orig in original_map.items():
        db = db_map.get(name)
        if not db:
            print(f"  MISSING in DB: {name}")
            all_match = False
            continue
        for key in ("E", "S", "G", "Final", "Band"):
            if orig[key] != db[key]:
                print(f"  MISMATCH {name}.{key}: original={orig[key]} db={db[key]}")
                all_match = False

    if all_match:
        print("  ALL SCORES MATCH — migration verified.")
    else:
        print("  DISCREPANCIES FOUND — check above.")

    return all_match


# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  ESGrow Migration — Excel to Database")
    print("=" * 60)

    # Reset DB if --fresh flag
    if "--fresh" in sys.argv:
        print("\n[FRESH] Dropping all tables...")
        from database import Base
        Base.metadata.drop_all(engine)

    init_db()
    session = get_session()

    try:
        seed_sectors(session)
        seed_indicator_definitions(session)
        seed_companies(session)
        import_indicator_scores(session)
        results = calculate_and_store_scores(session)
        verify_against_json(results)

        # Export DB results to output.json as sanity check
        results.sort(key=lambda x: x["Final"], reverse=True)
        export_path = os.path.join(BASE_DIR, "data", "output_db.json")
        with open(export_path, "w") as f:
            json.dump(results, f, indent=4)
        print(f"\n  DB export saved to {export_path}")

    finally:
        session.close()

    print("\n" + "=" * 60)
    print("  Migration complete.")
    print("=" * 60)
