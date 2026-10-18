"""
figures.py - Checks the figures in an answer against the sources it was written from.

Two kinds of problem are found:
  1. a figure that is not in any retrieved source (within its rounding), e.g. "$90 billion"
     when no source has it, or a figure the model worked out itself
  2. a badly formatted figure, e.g. "77,7 billion" (grouping must be 77.7 or 77,700)

Figures are compared by value, so "77.7 billion" matches "77,673 million". A figure is
checked only when it looks like one (currency sign, scale word, %, separators or a decimal),
so years, day numbers and citation numbers are ignored. Lines that say "calculated" are
skipped: a calculated figure is labelled, and its inputs are checked.
"""

# --- Imports -----------------------------------------------------------------
# re: finds numbers in text.
import re
from dataclasses import dataclass

# --- Patterns and settings -----------------------------------------------------------
# A number with optional currency sign, grouping or decimals, and an optional scale word or %.
NUMBER = re.compile(
    r"(?<![\w.])(?P<cur>[$€£₹]\s?)?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<dec>\.\d+)?"
    r"(?P<scale>\s?(?:billion|million|thousand|crore|lakh)\b|%)?",
    re.IGNORECASE,
)
# A comma followed by one or two digits that is neither Western nor Indian grouping: "77,7", "1,2".
MALFORMED = re.compile(r"(?<![\d,])\d{1,2},\d{1,2}(?![\d,])")
SCALES = {"thousand": 1e3, "lakh": 1e5, "million": 1e6, "crore": 1e7, "billion": 1e9}
# A source figure may be quoted in any of these units, so "77,673 million" matches "77.7 billion".
UNIT_FACTORS = (1, 1e3, 1e5, 1e6, 1e7, 1e9)


@dataclass(frozen=True)
class Figure:
    shown: str        # the text as written, e.g. "$77.7 billion"
    value: float      # in base units, e.g. 77.7e9
    half_unit: float  # half of the last displayed digit, in base units (the rounding allowed)


def _parts(match: re.Match) -> tuple[float, int, float]:
    """(number as written, decimal places shown, unit size of the scale word)."""
    text = match.group("num").replace(",", "") + (match.group("dec") or "")
    decimals = len(match.group("dec")) - 1 if match.group("dec") else 0
    scale = (match.group("scale") or "").strip().lower()
    return float(text), decimals, SCALES.get(scale, 1.0)


def is_figure(match: re.Match) -> bool:
    """A number that looks like a figure: currency, scale word, %, grouping or decimals."""
    return bool(match.group("cur") or match.group("scale") or match.group("dec") or "," in match.group("num"))


def figures_in(text: str) -> list[Figure]:
    """Every figure in the text, skipping 'calculated' lines and badly formatted figures."""
    found = []
    for line in text.splitlines():
        if "calculated" in line.lower():
            continue
        bad = [m.span() for m in MALFORMED.finditer(line)]
        for match in NUMBER.finditer(line):
            overlaps_bad = any(match.start() < end and start < match.end() for start, end in bad)
            if not is_figure(match) or overlaps_bad:
                continue
            number, decimals, unit = _parts(match)
            half = 0.5 * 10 ** -decimals * (1 if match.group("scale") == "%" else unit)
            found.append(Figure(match.group(0).strip(), number * unit, half))
    return found


def malformed_in(text: str) -> list[str]:
    """Badly formatted figures in the text (not in 'calculated' lines)."""
    return [m.group(0) for line in text.splitlines() if "calculated" not in line.lower()
            for m in MALFORMED.finditer(line)]


def source_numbers(texts: list[str]) -> list[float]:
    """Every number in the sources, in every unit it could be quoted in."""
    numbers = []
    for text in texts:
        for match in NUMBER.finditer(text):
            number, _, _ = _parts(match)
            numbers += [number * factor for factor in UNIT_FACTORS]
    return numbers


def figure_problems(answer: str, source_texts: list[str]) -> list[str]:
    """Figures in the answer that are badly formatted or not found in the sources. Empty = all good."""
    problems = malformed_in(answer)
    numbers = source_numbers(source_texts)
    for figure in figures_in(answer):
        if not any(abs(figure.value - number) <= figure.half_unit for number in numbers):
            problems.append(figure.shown)
    return problems
