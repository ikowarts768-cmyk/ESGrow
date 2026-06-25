"""
ESGrow Web Scraper
Checks company IR pages for new annual reports, downloads PDFs,
and extracts text for AI scoring.

Usage:
  from scraper import scrape_all
  new_reports = scrape_all(db_session)
"""

import os
import re
import hashlib
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from data_sources import DATA_SOURCES, SOURCES_BY_CODE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "data", "downloads")

# Be polite — identify ourselves and don't hammer servers
HEADERS = {
    "User-Agent": "ESGrow/1.0 (ESG Research Bot; contact: esgrow@example.com)",
}
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 2


def ensure_download_dir():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def find_pdf_links(page_url):
    """Visit a page and find all PDF download links."""
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [WARN] Could not fetch {page_url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    pdf_links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True).lower()

        # Look for PDF links
        if href.lower().endswith(".pdf") or "pdf" in text:
            full_url = urljoin(page_url, href)
            pdf_links.append({
                "url": full_url,
                "text": link.get_text(strip=True),
            })

    return pdf_links


def guess_report_year(url, link_text):
    """Try to extract the report year from URL or link text."""
    current_year = datetime.now().year
    combined = f"{url} {link_text}"

    # Look for 4-digit years in the URL or text
    years = re.findall(r"20[1-3]\d", combined)
    if years:
        # Return the most recent valid year
        valid_years = [int(y) for y in years if int(y) <= current_year]
        if valid_years:
            return max(valid_years)

    return current_year


def check_for_new_reports(company_source, session):
    """Check a company's IR pages for new reports not yet in FetchLog."""
    from models import FetchLog

    code = company_source["code"]
    ir_urls = company_source.get("ir_urls", [])
    patterns = company_source.get("report_patterns", [])

    if not ir_urls:
        return []

    new_reports = []

    for page_url in ir_urls:
        print(f"  Checking {page_url}...")
        pdf_links = find_pdf_links(page_url)
        time.sleep(DELAY_BETWEEN_REQUESTS)

        for link in pdf_links:
            link_text = link["text"].lower()
            url = link["url"]

            # Check if any pattern matches
            matches_pattern = not patterns or any(
                p.lower() in link_text or p.lower() in url.lower()
                for p in patterns
            )

            if not matches_pattern:
                continue

            # Check if we already processed this URL
            existing = (
                session.query(FetchLog)
                .filter_by(source_url=url)
                .first()
            )
            if existing:
                continue

            year = guess_report_year(url, link["text"])
            new_reports.append({
                "url": url,
                "text": link["text"],
                "report_year": year,
            })

    return new_reports


def download_pdf(url, company_code):
    """Download a PDF file. Returns the local file path."""
    ensure_download_dir()

    # Create a safe filename from the URL
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{company_code}_{url_hash}.pdf"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(filepath):
        print(f"  [SKIP] Already downloaded: {filename}")
        return filepath

    try:
        print(f"  Downloading {url}...")
        response = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"  [OK] Saved {filename} ({size_mb:.1f} MB)")
        return filepath

    except requests.RequestException as e:
        print(f"  [ERROR] Download failed: {e}")
        return None


def extract_text_from_pdf(pdf_path, max_chars=100000):
    """Extract text from a PDF using pdfplumber. Truncates to max_chars."""
    try:
        import pdfplumber
    except ImportError:
        print("  [ERROR] pdfplumber not installed. Run: pip install pdfplumber")
        return None

    try:
        text_parts = []
        total_chars = 0

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                total_chars += len(page_text)

                if total_chars >= max_chars:
                    break

        full_text = "\n\n".join(text_parts)
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars]

        print(f"  [OK] Extracted {len(full_text):,} characters from {os.path.basename(pdf_path)}")
        return full_text

    except Exception as e:
        print(f"  [ERROR] PDF extraction failed: {e}")
        return None


def file_hash(filepath):
    """Compute SHA-256 hash of a file for deduplication."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def scrape_all(session, company_codes=None):
    """
    Check all companies for new annual reports.
    Downloads PDFs and extracts text.

    Returns a list of dicts:
      [{code, report_year, text, source_url, file_hash}, ...]
    """
    sources = DATA_SOURCES
    if company_codes:
        sources = [s for s in DATA_SOURCES if s["code"] in company_codes]

    results = []

    for source in sources:
        code = source["code"]
        print(f"\n[{code}] {source['display_name']}")

        try:
            new_reports = check_for_new_reports(source, session)

            if not new_reports:
                print(f"  No new reports found.")
                continue

            for report in new_reports:
                print(f"  Found: {report['text']} (year: {report['report_year']})")

                # Download PDF
                pdf_path = download_pdf(report["url"], code)
                if not pdf_path:
                    continue

                # Extract text
                text = extract_text_from_pdf(pdf_path)
                if not text or len(text) < 500:
                    print(f"  [SKIP] Too little text extracted ({len(text) if text else 0} chars)")
                    continue

                results.append({
                    "code": code,
                    "report_year": report["report_year"],
                    "text": text,
                    "source_url": report["url"],
                    "file_hash": file_hash(pdf_path),
                })

        except Exception as e:
            print(f"  [ERROR] {code}: {e}")
            continue

    print(f"\n{'=' * 40}")
    print(f"Scraping complete: {len(results)} new reports found")
    return results


if __name__ == "__main__":
    from database import get_session

    session = get_session()
    try:
        results = scrape_all(session)
        for r in results:
            print(f"  {r['code']} ({r['report_year']}): {len(r['text']):,} chars")
    finally:
        session.close()
