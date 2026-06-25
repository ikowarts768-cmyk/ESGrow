# ESGrow Scoring Engine v2.0
# Reads from database, calculates ESG scores, writes results back.
# Fallback: can still read from Excel with --excel flag.

import json
import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Fallback weights (used if DB is unavailable) ────────────

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
SECTOR_WEIGHTS = {
    "Mining":         {"E": 0.50, "S": 0.30, "G": 0.20},
    "Banking":        {"E": 0.15, "S": 0.35, "G": 0.50},
    "Energy":         {"E": 0.42, "S": 0.33, "G": 0.25},
    "Agriculture":    {"E": 0.42, "S": 0.33, "G": 0.25},
    "Telecoms":       {"E": 0.15, "S": 0.40, "G": 0.45},
    "Consumer Goods": {"E": 0.22, "S": 0.38, "G": 0.40},
    "Manufacturing":  {"E": 0.45, "S": 0.30, "G": 0.25},
}

# ── Score bands ─────────────────────────────────────────────

def get_band(score):
    if score >= 80: return "ESG Leader"
    if score >= 60: return "ESG Performer"
    if score >= 40: return "Developing"
    if score >= 20: return "Laggard"
    return "Critical Risk"

# ── Pure scoring functions (unchanged) ──────────────────────

def calculate_pillar_score(indicators, weights):
    score = 0
    total_weight = 0
    for key, weight in weights.items():
        if key in indicators and indicators[key] is not None:
            score += indicators[key] * weight
            total_weight += weight
    return score / total_weight if total_weight > 0 else 0


def calculate_esg_score(company_data, sector_weights=None):
    sector = company_data["sector"]
    weights = sector_weights or SECTOR_WEIGHTS[sector]

    E_data = {k: v for k, v in company_data.items() if k.startswith("E")}
    S_data = {k: v for k, v in company_data.items() if k.startswith("S")}
    G_data = {k: v for k, v in company_data.items() if k.startswith("G")}

    E_score = calculate_pillar_score(E_data, E_WEIGHTS)
    S_score = calculate_pillar_score(S_data, S_WEIGHTS)
    G_score = calculate_pillar_score(G_data, G_WEIGHTS)

    final_score = (
        E_score * weights["E"] +
        S_score * weights["S"] +
        G_score * weights["G"]
    )

    return {
        "E": round(E_score, 1),
        "S": round(S_score, 1),
        "G": round(G_score, 1),
        "Final": round(final_score, 1),
        "Band": get_band(final_score),
    }

# ── Database scoring ────────────────────────────────────────

def run_scoring(session, report_year=None, notes=None):
    """Calculate scores for all active companies from DB data.
    Also snapshots each result into ScoreHistory for trend tracking.
    Returns sorted list of result dicts."""
    from models import Company, Sector, IndicatorScore, Score, ScoreHistory

    now = datetime.now(timezone.utc)
    companies = session.query(Company).filter_by(is_active=True).all()

    results = []
    for company in companies:
        sector = company.sector

        # Build indicator dict from DB
        indicators = {}
        for iscore in company.indicator_scores:
            indicators[iscore.indicator_id] = iscore.score

        company_data = {"sector": sector.name, **indicators}
        sector_w = {"E": sector.weight_e, "S": sector.weight_s, "G": sector.weight_g}
        score = calculate_esg_score(company_data, sector_w)

        # Upsert current score
        existing = session.query(Score).filter_by(company_id=company.id).first()
        if existing:
            existing.e_score = score["E"]
            existing.s_score = score["S"]
            existing.g_score = score["G"]
            existing.final_score = score["Final"]
            existing.band = score["Band"]
            existing.calculated_at = now
        else:
            session.add(Score(
                company_id=company.id,
                e_score=score["E"], s_score=score["S"], g_score=score["G"],
                final_score=score["Final"], band=score["Band"],
                calculated_at=now,
            ))

        # Snapshot into score_history for trend tracking
        session.add(ScoreHistory(
            company_id=company.id,
            e_score=score["E"], s_score=score["S"], g_score=score["G"],
            final_score=score["Final"], band=score["Band"],
            calculated_at=now,
            report_year=report_year,
            notes=notes,
        ))

        results.append({
            "Company": company.name,
            "Sector": sector.name,
            "E": score["E"],
            "S": score["S"],
            "G": score["G"],
            "Final": score["Final"],
            "Band": score["Band"],
        })

    session.commit()
    results.sort(key=lambda x: x["Final"], reverse=True)
    return results


def export_json(results, path=None):
    """Write results to output.json."""
    if path is None:
        path = os.path.join(BASE_DIR, "data", "output.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=4)
    return path

# ── Legacy Excel loader (kept for --excel mode) ────────────

def load_company_from_sheet(file_path, sheet_name, sector):
    import pandas as pd

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=4)
    df.columns = df.columns.str.strip().str.replace('\u2013', '-').str.replace('\u2014', '-')

    score_col = None
    for col in df.columns:
        if str(col).startswith("Score"):
            score_col = col
            break

    if score_col is None:
        print(f"  WARNING: No score column found in sheet '{sheet_name}'.")
        return {"company": sheet_name, "sector": sector}

    company_data = {"company": sheet_name, "sector": sector}

    for _, row in df.iterrows():
        indicator = str(row.iloc[0]).strip()
        if len(indicator) == 3 and indicator[0] in ("E", "S", "G") and indicator[1:].isdigit():
            raw_score = row[score_col]
            if pd.notna(raw_score):
                try:
                    score_str = str(raw_score).strip()
                    numeric = float(score_str.split()[0].split("\u2014")[0].split("-")[0])
                    if 0 <= numeric <= 100:
                        company_data[indicator] = numeric
                except (ValueError, IndexError):
                    pass

    return company_data

# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":

    if "--excel" in sys.argv:
        # Legacy Excel mode
        import pandas as pd

        file_path = os.path.join(BASE_DIR, "data", "ESGrow_Zambia_Complete_v1.0.xlsx")
        companies = [
            ("SCB_ZAMBIA", "Banking"), ("CEC", "Energy"),
            ("ZBL", "Consumer Goods"), ("ZANACO", "Banking"),
            ("AIRTEL", "Telecoms"), ("ZAMSUG", "Agriculture"),
            ("FQM", "Mining"), ("ZCCM", "Mining"),
            ("LAFARGE", "Manufacturing"), ("MTN_ZAMBIA", "Telecoms"),
        ]

        print("\nLoading company data from Excel...\n")
        results = []
        for sheet, sector in companies:
            data = load_company_from_sheet(file_path, sheet, sector)
            score = calculate_esg_score(data)
            results.append({
                "Company": sheet, "Sector": sector,
                "E": score["E"], "S": score["S"], "G": score["G"],
                "Final": score["Final"], "Band": score["Band"],
            })
        results.sort(key=lambda x: x["Final"], reverse=True)

    else:
        # Database mode (default)
        from database import get_session
        session = get_session()
        try:
            results = run_scoring(session)
        finally:
            session.close()

    # Print leaderboard
    print("\n" + "=" * 65)
    print("  ESGrow Leaderboard — Zambia 2025")
    print("=" * 65)
    print(f"  {'#':<4} {'Company':<16} {'Sector':<16} {'E':>5} {'S':>5} {'G':>5} {'Score':>7}  Band")
    print("-" * 65)
    for i, r in enumerate(results, 1):
        print(f"  {i:<4} {r['Company']:<16} {r['Sector']:<16} {r['E']:>5} {r['S']:>5} {r['G']:>5} {r['Final']:>7}  {r['Band']}")
    print("=" * 65)

    # Export JSON
    path = export_json(results)
    print(f"\n  Results saved to {path}")
