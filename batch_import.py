"""
ESGrow Phase 3 — Batch CSV importer.

Reads a CSV file of scored companies and inserts them into the database,
then recomputes pillar / final / band scores for every active company.

Usage:
    python batch_import.py data/phase3_template.csv
    python batch_import.py data/phase3_template.csv --dry-run
    python batch_import.py data/phase3_template.csv --replace     # overwrite existing rows

CSV schema (one row per company):
    code, display_name, sector, report_year, report_source,
    E01..E08, S01..S08, G01..G08, notes

All 24 indicator columns are required and must be integers in [0, 100].
Sector must already exist in the `sectors` table.
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

from database import SessionLocal, init_db
from models import (
    Sector, Company, IndicatorDefinition, IndicatorScore, Score, ScoreHistory,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Weights (must match migrate.py) ─────────────────────────

E_WEIGHTS = {"E01": 0.20, "E02": 0.18, "E03": 0.15, "E04": 0.14,
             "E05": 0.13, "E06": 0.12, "E07": 0.05, "E08": 0.03}
S_WEIGHTS = {"S01": 0.22, "S02": 0.18, "S03": 0.14, "S04": 0.14,
             "S05": 0.12, "S06": 0.10, "S07": 0.06, "S08": 0.04}
G_WEIGHTS = {"G01": 0.22, "G02": 0.18, "G03": 0.17, "G04": 0.14,
             "G05": 0.13, "G06": 0.08, "G07": 0.05, "G08": 0.03}

ALL_INDICATORS = list(E_WEIGHTS) + list(S_WEIGHTS) + list(G_WEIGHTS)  # 24 codes
REQUIRED_META = ["code", "display_name", "sector", "report_year", "report_source"]
REQUIRED_COLUMNS = REQUIRED_META + ALL_INDICATORS  # notes is optional


# ── Helpers ─────────────────────────────────────────────────

def get_band(score: float) -> str:
    if score >= 80: return "ESG Leader"
    if score >= 60: return "ESG Performer"
    if score >= 40: return "Developing"
    if score >= 20: return "Laggard"
    return "Critical Risk"


def pillar_score(indicators: dict, weights: dict) -> float:
    score = 0.0
    total = 0.0
    for key, w in weights.items():
        v = indicators.get(key)
        if v is not None:
            score += v * w
            total += w
    return score / total if total > 0 else 0.0


# ── Validation ──────────────────────────────────────────────

def validate_row(row: dict, row_num: int, valid_sectors: set, errors: list):
    # Required metadata present & non-empty
    for col in REQUIRED_META:
        if col not in row or not str(row[col]).strip():
            errors.append(f"Row {row_num} ({row.get('code', '?')}): missing '{col}'")

    # Sector exists
    sector = str(row.get("sector", "")).strip()
    if sector and sector not in valid_sectors:
        errors.append(
            f"Row {row_num} ({row.get('code', '?')}): sector '{sector}' not in DB. "
            f"Valid: {sorted(valid_sectors)}"
        )

    # report_year parseable
    try:
        int(row.get("report_year", ""))
    except (ValueError, TypeError):
        errors.append(f"Row {row_num} ({row.get('code', '?')}): report_year not an integer")

    # 24 indicator values present, integer-like, in [0,100]
    for ind in ALL_INDICATORS:
        raw = row.get(ind, "")
        if raw is None or str(raw).strip() == "":
            errors.append(f"Row {row_num} ({row.get('code', '?')}): missing score for {ind}")
            continue
        try:
            v = float(raw)
        except ValueError:
            errors.append(f"Row {row_num} ({row.get('code', '?')}): {ind}='{raw}' not numeric")
            continue
        if not (0 <= v <= 100):
            errors.append(f"Row {row_num} ({row.get('code', '?')}): {ind}={v} out of [0,100]")


def load_and_validate(csv_path: str, session) -> list:
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found: {csv_path}")
        sys.exit(1)

    valid_sectors = {s.name for s in session.query(Sector).all()}
    if not valid_sectors:
        print("ERROR: No sectors in DB. Run `python migrate.py` first.")
        sys.exit(1)

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            print(f"ERROR: CSV missing required columns: {missing}")
            sys.exit(1)

        rows = list(reader)

    if not rows:
        print("ERROR: CSV has no data rows.")
        sys.exit(1)

    errors = []
    seen_codes = set()
    for i, row in enumerate(rows, start=2):  # header is line 1
        code = str(row.get("code", "")).strip().upper()
        if code in seen_codes:
            errors.append(f"Row {i}: duplicate code '{code}' within CSV")
        seen_codes.add(code)
        validate_row(row, i, valid_sectors, errors)

    if errors:
        print(f"\nVALIDATION FAILED — {len(errors)} issue(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print(f"[validate] {len(rows)} row(s) OK. Sectors: {sorted(valid_sectors)}")
    return rows


# ── Import ──────────────────────────────────────────────────

def upsert_company(session, row: dict, replace: bool) -> tuple:
    """Return (company, action) where action in {'inserted', 'updated', 'skipped'}."""
    code = str(row["code"]).strip().upper()
    sector = session.query(Sector).filter_by(name=row["sector"].strip()).first()

    company = session.query(Company).filter_by(name=code).first()
    if company and not replace:
        return company, "skipped"

    if company:
        company.display_name = row["display_name"].strip()
        company.sector_id = sector.id
        company.is_active = True
        # Wipe existing indicator rows so we don't double-count
        session.query(IndicatorScore).filter_by(company_id=company.id).delete()
        action = "updated"
    else:
        company = Company(
            name=code,
            display_name=row["display_name"].strip(),
            sector_id=sector.id,
            is_active=True,
        )
        session.add(company)
        session.flush()  # need company.id
        action = "inserted"

    for ind in ALL_INDICATORS:
        session.add(IndicatorScore(
            company_id=company.id,
            indicator_id=ind,
            score=float(row[ind]),
            raw_value=None,
            unit=None,
            source=row.get("report_source", "").strip() or None,
        ))

    return company, action


def recompute_scores(session, only_company_ids: set = None, report_year: int = None):
    """Recalculate Score + append ScoreHistory for affected companies."""
    now = datetime.now(timezone.utc)
    q = session.query(Company).filter(Company.is_active == True)
    if only_company_ids:
        q = q.filter(Company.id.in_(only_company_ids))

    summary = []
    for company in q.all():
        inds = {s.indicator_id: s.score for s in company.indicator_scores}
        e = pillar_score(inds, E_WEIGHTS)
        s_ = pillar_score(inds, S_WEIGHTS)
        g = pillar_score(inds, G_WEIGHTS)
        sector = company.sector
        final = e * sector.weight_e + s_ * sector.weight_s + g * sector.weight_g
        band = get_band(final)

        e_r, s_r, g_r, f_r = round(e, 1), round(s_, 1), round(g, 1), round(final, 1)

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

        session.add(ScoreHistory(
            company_id=company.id,
            e_score=e_r, s_score=s_r, g_score=g_r,
            final_score=f_r, band=band, calculated_at=now,
            report_year=report_year,
            notes="Phase 3 batch import",
        ))

        summary.append((company.name, e_r, s_r, g_r, f_r, band))

    return summary


# ── Main ────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="ESGrow Phase 3 CSV batch importer")
    ap.add_argument("csv_path", help="Path to CSV file")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate only; don't write to DB")
    ap.add_argument("--replace", action="store_true",
                    help="Overwrite companies that already exist")
    args = ap.parse_args()

    init_db()
    session = SessionLocal()

    try:
        rows = load_and_validate(args.csv_path, session)

        if args.dry_run:
            print("[dry-run] Validation passed. No DB writes.")
            for r in rows:
                print(f"  - {r['code']:15s} | {r['sector']:15s} | {r['display_name']}")
            return

        inserted, updated, skipped = 0, 0, 0
        touched_ids = set()
        report_year = None

        for row in rows:
            company, action = upsert_company(session, row, args.replace)
            touched_ids.add(company.id)
            if action == "inserted": inserted += 1
            elif action == "updated": updated += 1
            else: skipped += 1
            if report_year is None:
                try:
                    report_year = int(row["report_year"])
                except (ValueError, KeyError):
                    pass

        session.commit()
        print(f"\n[import] inserted={inserted} updated={updated} skipped={skipped}")
        if skipped:
            print("  (Re-run with --replace to overwrite skipped rows.)")

        # Recompute all active companies — ranking depends on full set
        print("\n[recompute] Recalculating pillar/final/band for all active companies...")
        summary = recompute_scores(session, report_year=report_year)
        session.commit()

        touched_summary = [s for s in summary if any(
            s[0] == str(r["code"]).strip().upper() for r in rows
        )]
        print(f"\n[done] {len(touched_summary)} company score(s) from this CSV:")
        for name, e, s_, g, f, b in touched_summary:
            print(f"  {name:15s}  E={e:>5}  S={s_:>5}  G={g:>5}  Final={f:>5}  {b}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
