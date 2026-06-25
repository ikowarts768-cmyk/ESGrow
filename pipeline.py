"""
ESGrow Data Pipeline
Orchestrates the full flow: scrape → AI score → update DB → snapshot history.

Usage:
  python pipeline.py                    # Process all companies
  python pipeline.py --company FQM      # Process one company
  python pipeline.py --quick            # Recalculate only (no scraping)
"""

import argparse
import sys
from datetime import datetime, timezone

from database import get_session, init_db
from data_sources import SOURCES_BY_CODE
import scraper
import ai_scorer
import engine


def upsert_indicator_scores(session, company, scores_dict, report_year, source_url):
    """Update indicator scores in the database for a company."""
    from models import IndicatorScore

    updated = 0
    now = datetime.now(timezone.utc)

    for indicator_id, score_value in scores_dict.items():
        existing = (
            session.query(IndicatorScore)
            .filter_by(company_id=company.id, indicator_id=indicator_id)
            .first()
        )

        if existing:
            existing.score = score_value
            existing.report_year = report_year
            existing.updated_at = now
            existing.source = source_url
        else:
            session.add(IndicatorScore(
                company_id=company.id,
                indicator_id=indicator_id,
                score=score_value,
                report_year=report_year,
                updated_at=now,
                source=source_url,
            ))

        updated += 1

    return updated


def log_fetch(session, company_id, report_year, source_url, file_hash, status, notes=None):
    """Write a FetchLog entry to track what was processed."""
    from models import FetchLog

    session.add(FetchLog(
        company_id=company_id,
        report_year=report_year,
        source_url=source_url,
        file_hash=file_hash,
        status=status,
        notes=notes,
    ))


def run_pipeline(session, company_codes=None, quick=False):
    """
    Main pipeline: scrape → AI score → update indicators → recalculate → snapshot history.

    Args:
        session: SQLAlchemy session
        company_codes: list of company codes to process (None = all)
        quick: if True, skip scraping and just recalculate existing data

    Returns:
        Summary dict with counts of what happened
    """
    from models import Company

    summary = {
        "companies_checked": 0,
        "reports_found": 0,
        "scores_updated": 0,
        "errors": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    if quick:
        print("\n[QUICK MODE] Recalculating scores from existing data...")
        results = engine.run_scoring(session, notes="Quick recalculation")
        engine.export_json(results)
        summary["scores_updated"] = len(results)
        print(f"[OK] Recalculated {len(results)} companies")
        return summary

    # Full pipeline: scrape → score → update
    print("\n" + "=" * 50)
    print("  ESGrow Pipeline — Full Run")
    print("=" * 50)

    # Step 1: Scrape for new reports
    print("\n[STEP 1] Scraping for new annual reports...")
    new_reports = scraper.scrape_all(session, company_codes=company_codes)
    summary["companies_checked"] = len(company_codes) if company_codes else len(SOURCES_BY_CODE)
    summary["reports_found"] = len(new_reports)

    if not new_reports:
        print("\n[INFO] No new reports found. Running recalculation anyway...")
        results = engine.run_scoring(session, notes="Pipeline run — no new data")
        engine.export_json(results)
        summary["scores_updated"] = len(results)
        return summary

    # Step 2: AI-score each new report
    print(f"\n[STEP 2] AI-scoring {len(new_reports)} new reports...")

    for report in new_reports:
        code = report["code"]
        year = report["report_year"]

        print(f"\n  Processing {code} ({year})...")

        # Find the company in the database
        company = session.query(Company).filter_by(name=code).first()
        if not company:
            error = f"Company {code} not found in database"
            print(f"  [ERROR] {error}")
            summary["errors"].append(error)
            continue

        source_info = SOURCES_BY_CODE.get(code, {})
        sector = source_info.get("sector", company.sector.name)

        # Send to Claude for scoring
        ai_result = ai_scorer.score_report(
            text=report["text"],
            company_name=source_info.get("display_name", code),
            sector=sector,
        )

        if not ai_result["success"]:
            error = f"AI scoring failed for {code}"
            print(f"  [ERROR] {error}")
            log_fetch(session, company.id, year, report["source_url"],
                      report.get("file_hash"), "failed", notes=error)
            summary["errors"].append(error)
            continue

        # Step 3: Update indicator scores in DB
        updated = upsert_indicator_scores(
            session, company, ai_result["scores"], year, report["source_url"]
        )
        print(f"  [OK] Updated {updated} indicator scores for {code}")

        # Log the successful fetch
        log_fetch(session, company.id, year, report["source_url"],
                  report.get("file_hash"), "scored",
                  notes=f"AI-scored {updated} indicators")

        summary["scores_updated"] += 1

    # Step 4: Recalculate all company scores and snapshot history
    print(f"\n[STEP 3] Recalculating all ESG scores...")
    most_recent_year = max(r["report_year"] for r in new_reports) if new_reports else None
    results = engine.run_scoring(
        session,
        report_year=most_recent_year,
        notes=f"Pipeline auto-update ({summary['reports_found']} new reports)",
    )
    engine.export_json(results)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(f"\n{'=' * 50}")
    print(f"  Pipeline Complete!")
    print(f"  Companies checked: {summary['companies_checked']}")
    print(f"  New reports found: {summary['reports_found']}")
    print(f"  Scores updated:    {summary['scores_updated']}")
    print(f"  Errors:            {len(summary['errors'])}")
    print(f"{'=' * 50}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESGrow Data Pipeline")
    parser.add_argument("--company", type=str, help="Process a single company by code (e.g. FQM)")
    parser.add_argument("--quick", action="store_true", help="Recalculate only, skip scraping")
    args = parser.parse_args()

    init_db()
    session = get_session()

    try:
        company_codes = [args.company] if args.company else None
        summary = run_pipeline(session, company_codes=company_codes, quick=args.quick)

        if summary["errors"]:
            print("\nErrors encountered:")
            for err in summary["errors"]:
                print(f"  - {err}")
            sys.exit(1)

    finally:
        session.close()
