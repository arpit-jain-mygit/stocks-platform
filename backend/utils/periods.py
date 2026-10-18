"""
periods.py - Turns a period like "Q3 FY25" into structured fields, for any company.

Every company has its own financial year (FY). It ends on the last day of the
company's year-end month (companies.fy_end_month in Postgres), and the FY is
named after the calendar year it ends in:

    year ends in March (India, Japan, UK)      FY25 = 1 Apr 2024 - 31 Mar 2025
    year ends in December (most US / EU)       FY25 = 1 Jan 2025 - 31 Dec 2025
    year ends in September (e.g. Apple)        FY25 = 1 Oct 2024 - 30 Sep 2025
    year ends in June (Australia)              FY25 = 1 Jul 2024 - 30 Jun 2025

Q1-Q4 are the four 3-month quarters of that year; Q4 ends on the year-end.

    parse_period("Q3 FY25")                    (default: year ends in March)
      -> Period(fiscal_year=2025, quarter=3, period_end=date(2024, 12, 31),
                label="Q3 FY25 (quarter ended 31-Dec-2024)")
    parse_period("Q3 2025", fy_end_month=12)   -> quarter ended 30-Sep-2025
    parse_period("FY25", fy_end_month=9)       -> year ended 30-Sep-2025

Accepted input: "Q3 FY25", "Q3 FY2025", "q3fy25", "FY25", "FY 2025", "Q3 2025",
"2025", or a full label like "Q3 FY25 (quarter ended 31-Dec-2024)" (only the
start is read). A plain year ("2025") means the financial year ending in 2025.

Stored fields (fiscal_year, quarter, period_end) are what filters use. Note that
fiscal_year and quarter never depend on the year-end month - "Q3 FY25" is the
same filter for every company - only period_end and the label do.
"""

# --- Imports -----------------------------------------------------------------
# re:         reads "Q3 FY25" style text.
# calendar:   last day of a month (28 / 29 / 30 / 31).
# dataclass:  simple record class (Period).
# date:       quarter / year end dates.
import calendar
import re
from dataclasses import dataclass
from datetime import date

# --- Settings ----------------------------------------------------------------
# Year-end month used when a company has none recorded (3 = March).
DEFAULT_FY_END_MONTH = 3

# "Q3 FY25", "FY2025", "Q3 2025", "2025" ... (Q part optional; a 2-digit year needs "FY").
PATTERN = re.compile(r"^\s*(?:Q([1-4])\s*)?(?:FY\s*(\d{4}|\d{2})|(\d{4}))\b", re.IGNORECASE)


@dataclass(frozen=True)
class Period:
    fiscal_year: int        # e.g. 2025 for FY25 (the calendar year the FY ends in)
    quarter: int | None     # 1-4, or None for a full year
    period_end: date
    label: str              # e.g. "Q3 FY25 (quarter ended 31-Dec-2024)"

    def fields(self) -> dict:
        """The values stored on chunks and document records."""
        return {"fiscal_year": self.fiscal_year, "quarter": self.quarter,
                "period_end": self.period_end.isoformat(), "period": self.label}


def month_end(month_index: int) -> date:
    """
    Last day of a month given as one running number, month_index = year*12 + (month-1),
    so "3 months earlier" is just "- 3". E.g. 2024*12 + 11 -> 31-Dec-2024.
    """
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_period(text: str, fy_end_month: int = DEFAULT_FY_END_MONTH) -> Period:
    """
    Parses "Q3 FY25" / "FY25" / "Q3 2025" style text for a company whose financial
    year ends in fy_end_month (1-12). Raises ValueError if the text can't be read.
    """
    if not 1 <= fy_end_month <= 12:
        raise ValueError(f"fy_end_month must be 1-12, not {fy_end_month}")
    match = PATTERN.match(text or "")
    if not match:
        raise ValueError(f"Can't read period {text!r}. Use e.g. 'Q3 FY25', 'FY25' or 'Q3 2025'.")
    quarter = int(match.group(1)) if match.group(1) else None
    year = int(match.group(2) or match.group(3))
    fiscal_year = year + 2000 if year < 100 else year
    short = f"FY{fiscal_year % 100:02d}"

    # The year ends on the last day of fy_end_month in `fiscal_year`; each earlier
    # quarter ends 3 months before the next one (Q4 = the year-end).
    year_end_index = fiscal_year * 12 + fy_end_month - 1
    if quarter is None:
        end = month_end(year_end_index)
        return Period(fiscal_year, None, end, f"{short} (year ended {end:%d-%b-%Y})")

    end = month_end(year_end_index - 3 * (4 - quarter))
    return Period(fiscal_year, quarter, end, f"Q{quarter} {short} (quarter ended {end:%d-%b-%Y})")
