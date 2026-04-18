"""SEC 8-K item code → plain-English title map.

8-K filings carry one or more item codes (e.g. "2.02,7.01") indicating which
events triggered the filing. EDGAR's submissions index exposes those codes but
not the filing body, so without expansion the sentiment scorer sees only the
raw numeric codes and returns ~0.0 regardless of materiality.

This module expands codes into their official SEC titles, giving TextBlob
scoreable English while staying neutral (we don't inject valence — the titles
are the canonical SEC descriptors).
"""

from __future__ import annotations

ITEM_CODE_TITLES: dict[str, str] = {
    # Section 1 — Registrant's Business and Operations
    "1.01": "Entry into a Material Definitive Agreement",
    "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "1.04": "Mine Safety - Reporting of Shutdowns and Patterns of Violations",
    "1.05": "Material Cybersecurity Incidents",
    # Section 2 — Financial Information
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    # Section 3 — Securities and Trading Markets
    "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    # Section 4 — Matters Related to Accountants and Financial Statements
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    # Section 5 — Corporate Governance and Management
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure or Appointment of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.04": "Temporary Suspension of Trading Under Employee Benefit Plans",
    "5.05": "Amendments to Code of Ethics",
    "5.06": "Change in Shell Company Status",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "5.08": "Shareholder Director Nominations",
    # Section 6 — Asset-Backed Securities
    "6.01": "ABS Informational and Computational Material",
    "6.02": "Change of Servicer or Trustee",
    "6.03": "Change in Credit Enhancement or Other External Support",
    "6.04": "Failure to Make a Required Distribution",
    "6.05": "Securities Act Updating Disclosure",
    # Section 7 — Regulation FD
    "7.01": "Regulation FD Disclosure",
    # Section 8 — Other Events
    "8.01": "Other Events",
    # Section 9 — Financial Statements and Exhibits
    "9.01": "Financial Statements and Exhibits",
}


def expand_items(items_csv: str) -> str:
    """Turn ``"2.02,7.01"`` into a period-joined English string.

    Unknown codes are dropped silently — the SEC adds new items over time and
    a missed code is preferable to scoring raw "6.99" as text.
    """
    if not items_csv:
        return ""
    titles: list[str] = []
    for raw in items_csv.split(","):
        code = raw.strip()
        title = ITEM_CODE_TITLES.get(code)
        if title:
            titles.append(title)
    return ". ".join(titles)
