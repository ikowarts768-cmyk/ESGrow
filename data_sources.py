"""
ESGrow Data Sources Registry

Maps each company to where their annual reports can be found.
The scraper uses this to check for new reports automatically.

To add a new company:
  1. Add a new dict to DATA_SOURCES below
  2. Fill in the ir_urls with links to their investor relations page
  3. Add report_patterns — filename patterns to look for (e.g. "annual-report")
"""

DATA_SOURCES = [
    # ── Banking ──────────────────────────────────────────────
    {
        "code": "SCB_ZAMBIA",
        "display_name": "Standard Chartered Zambia",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.sc.com/en/investors/annual-report/",
        ],
        "report_patterns": ["annual-report", "sustainability"],
    },
    {
        "code": "ZANACO",
        "display_name": "Zanaco Bank",
        "sector": "Banking",
        "luse_ticker": "ZANACO",
        "ir_urls": [
            "https://www.zanaco.co.zm/investor-relations/",
        ],
        "report_patterns": ["annual-report", "esg-report"],
    },
    {
        "code": "STANBIC_ZM",
        "display_name": "Stanbic Bank Zambia Limited",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.stanbicbank.co.zm/zambia/About-Us/investor-relations",
        ],
        "report_patterns": ["annual-report"],
    },
    {
        "code": "ABSA_ZM",
        "display_name": "Absa Bank Zambia PLC",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.absa.co.zm/about-us/investor-relations/",
        ],
        "report_patterns": ["annual-report", "financial-statement"],
    },
    {
        "code": "FNB_ZM",
        "display_name": "First National Bank Zambia Limited",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.fnbzambia.co.zm/about-fnb/investor-relations.html",
        ],
        "report_patterns": ["annual-report"],
    },
    {
        "code": "ACCESS_ZM",
        "display_name": "Access Bank Zambia Limited",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.accessbankplc.com/investor-relations/",
        ],
        "report_patterns": ["annual-report"],
    },
    {
        "code": "MFS_ZM",
        "display_name": "Madison Financial Services PLC",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [],
        "report_patterns": ["annual-report", "financials"],
    },
    {
        "code": "PRIMA_ZM",
        "display_name": "Prima Reinsurance Plc (now Zambia Reinsurance Plc)",
        "sector": "Banking",
        "luse_ticker": "PRIMA",
        "ir_urls": [],
        "report_patterns": ["annual-report"],
    },
    {
        "code": "BAYPORT_ZM",
        "display_name": "Bayport Financial Services Zambia Limited",
        "sector": "Banking",
        "luse_ticker": None,
        "ir_urls": [],
        "report_patterns": ["annual-report", "esg-report"],
    },
    # ── Energy ───────────────────────────────────────────────
    {
        "code": "CEC",
        "display_name": "Copperbelt Energy Corporation",
        "sector": "Energy",
        "luse_ticker": "CEC",
        "ir_urls": [
            "https://www.cecinvestor.com/",
        ],
        "report_patterns": ["annual-report", "integrated-report"],
    },
    {
        "code": "PUMA_ZM",
        "display_name": "Puma Energy Zambia Plc",
        "sector": "Energy",
        "luse_ticker": None,
        "ir_urls": [
            "https://pumaenergy.com/en/investors",
        ],
        "report_patterns": ["annual-report", "integrated-report"],
    },
    {
        "code": "UNITRANS_ZM",
        "display_name": "Unitrans Zambia (KAP Limited division)",
        "sector": "Energy",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.kap.co.za/investor-centre/",
        ],
        "report_patterns": ["integrated-report"],
    },
    # ── Consumer Goods ───────────────────────────────────────
    {
        "code": "ZBL",
        "display_name": "Zambian Breweries",
        "sector": "Consumer Goods",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.ab-inbev.com/investors/",
        ],
        "report_patterns": ["annual-report", "sustainability"],
    },
    {
        "code": "SHOPRITE_ZM",
        "display_name": "Shoprite Holdings Limited (Zambia operations)",
        "sector": "Consumer Goods",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.shopriteholdings.co.za/investors.html",
        ],
        "report_patterns": ["integrated-report", "annual-report"],
    },
    {
        "code": "NATBREW",
        "display_name": "National Breweries Plc",
        "sector": "Consumer Goods",
        "luse_ticker": "NATBRW",
        "ir_urls": [],
        "report_patterns": ["annual-report"],
    },
    # ── Mining ───────────────────────────────────────────────
    {
        "code": "FQM",
        "display_name": "First Quantum Minerals",
        "sector": "Mining",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.first-quantum.com/English/investors/default.aspx",
        ],
        "report_patterns": ["annual-report", "esg", "sustainability"],
    },
    {
        "code": "ZCCM",
        "display_name": "ZCCM Investments Holdings",
        "sector": "Mining",
        "luse_ticker": "ZCCM-IH",
        "ir_urls": [
            "https://www.zccm-ih.com.zm/investor-relations/",
        ],
        "report_patterns": ["annual-report"],
    },
    # ── Agriculture ──────────────────────────────────────────
    {
        "code": "ZAMSUG",
        "display_name": "Zambia Sugar",
        "sector": "Agriculture",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.illovosugar.co.za/investors",
        ],
        "report_patterns": ["annual-report", "integrated-report"],
    },
    {
        "code": "ZAMBEEF",
        "display_name": "Zambeef Products PLC",
        "sector": "Agriculture",
        "luse_ticker": "ZAMBEEF",
        "ir_urls": [
            "https://www.zambeefplc.com/investors/",
        ],
        "report_patterns": ["annual-report"],
    },
    # ── Telecoms ─────────────────────────────────────────────
    {
        "code": "AIRTEL",
        "display_name": "Airtel Zambia",
        "sector": "Telecoms",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.airtel.in/ir/home",
        ],
        "report_patterns": ["annual-report", "sustainability"],
    },
    {
        "code": "MTN_ZAMBIA",
        "display_name": "MTN Zambia",
        "sector": "Telecoms",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.mtn.com/investors/",
        ],
        "report_patterns": ["annual-report", "esg", "integrated-report"],
    },
    # ── Manufacturing ────────────────────────────────────────
    {
        "code": "LAFARGE",
        "display_name": "Lafarge Zambia",
        "sector": "Manufacturing",
        "luse_ticker": None,
        "ir_urls": [
            "https://www.holcim.com/investors",
        ],
        "report_patterns": ["annual-report", "sustainability"],
    },
]

# Quick lookup by company code
SOURCES_BY_CODE = {s["code"]: s for s in DATA_SOURCES}
