"""
periods.py - Turns a period like "Q3 FY25" into structured fields.

Indian financial year (FY) runs April to March; FY25 = 1 Apr 2024 - 31 Mar 2025.
    Q1 = Apr-Jun (ends 30 Jun)   Q2 = Jul-Sep (ends 30 Sep)
    Q3 = Oct-Dec (ends 31 Dec)   Q4 = Jan-Mar (ends 31 Mar)

    parse_period("Q3 FY25")
      -> Period(fiscal_year=2025, quarter=3, period_end=date(2024, 12, 31),
                label="Q3 FY25 (quarter ended 31-Dec-2024)")
    parse_period("FY25") -> full year, quarter=None, ends 31-Mar-2025

Accepted input: "Q3 FY25", "Q3 FY2025", "q3fy25", "FY25", or a full label
like "Q3 FY25 (quarter ended 31-Dec-2024)" (only the start is read).
Stored fields (fiscal_year, quarter, period_end) are what filters use; the
label is only for display and for each chunk's label line.
"""

# --- Imports -----------------------------------------------------------------
# re:        reads "Q3 FY25" style text.
# dataclass: simple record class (Period).
# date:      quarter end dates.
import re
from dataclasses import dataclass
from datetime import date

# Quarter -> (month, day) it ends on, and whether that date falls in the
# calendar year BEFORE the financial year's number (Q1-Q3 do, Q4 doesn't).
QUARTER_END = {1: (6, 30, True), 2: (9, 30, True), 3: (12, 31, True), 4: (3, 31, False)}

PATTERN = re.compile(r"^\s*(?:Q([1-4])\s*)?FY\s*(\d{2}|\d{4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class Period:
    fiscal_year: int        # e.g. 2025 for FY25
    quarter: int | None     # 1-4, or None for a full year
    period_end: date
    label: str              # e.g. "Q3 FY25 (quarter ended 31-Dec-2024)"

    def fields(self) -> dict:
        """The values stored on chunks and document records."""
        return {"fiscal_year": self.fiscal_year, "quarter": self.quarter,
                "period_end": self.period_end.isoformat(), "period": self.label}


def parse_period(text: str) -> Period:
    """Parses "Q3 FY25" / "FY25" style text. Raises ValueError if it can't."""
    match = PATTERN.match(text or "")
    if not match:
        raise ValueError(f"Can't read period {text!r}. Use e.g. 'Q3 FY25' or 'FY25'.")
    quarter = int(match.group(1)) if match.group(1) else None
    year = int(match.group(2))
    fiscal_year = year + 2000 if year < 100 else year
    short = f"FY{fiscal_year % 100:02d}"

    if quarter is None:
        end = date(fiscal_year, 3, 31)
        return Period(fiscal_year, None, end, f"{short} (year ended {end:%d-%b-%Y})")

    month, day, previous_year = QUARTER_END[quarter]
    end = date(fiscal_year - 1 if previous_year else fiscal_year, month, day)
    return Period(fiscal_year, quarter, end, f"Q{quarter} {short} (quarter ended {end:%d-%b-%Y})")
