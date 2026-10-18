"""
run_eval.py - Runs the per-company eval sets against the /ask API and grades every answer.

Layout:
  eval/companies/<COMPANY_ID>/eval_set.json   hand-written questions + expected answers
  eval/results/<COMPANY_ID>/run-<time>.json   every run: expected vs actual, per case

How it works:
  1. Reads each company's eval_set.json (or only the ones given with --company).
  2. Sends each case's "request" to POST /ask on your running API.
  3. Grades the reply with fixed, repeatable checks (no AI involved):
       must_contain      - every required fact is in the answer
       must_not_contain  - no wrong-column / wrong number slipped in
       expected_pages    - at least one cited source is on the right page
       expect_not_found  - refusal cases must refuse
       accept_any_of     - ambiguous cases: any one valid interpretation
  4. Prints a pass/fail table + score per category per company, and saves each
     company's run (request, expected, actual, checks) to eval/results/<COMPANY_ID>/
     - ready for review or for another LLM to compare expected vs actual.
Cases marked "needs_judge" are flagged: passing the checks is necessary but
not sufficient for them - an LLM judge (or you) should read the answer too.

Run (API must be running:  uvicorn api.main:app):
  python eval/run_eval.py                          every company, every case
  python eval/run_eval.py --company OFSS           one company (repeatable)
  python eval/run_eval.py --company OFSS --only ofss-01 ofss-10
  python eval/run_eval.py --category prose_fact    one category
  python eval/run_eval.py --self-test              check the checks: grades the
                                                   expected answers, no API calls
"""

# --- Imports -----------------------------------------------------------------
# argparse:    command-line options.
# json, re:    reading the eval file, matching numbers in answers.
# time:        small pause between requests (free-tier rate limits).
# urllib:      plain HTTP calls to the API (no extra package needed).
# Path:          file paths.
# defaultdict:   counting passes per category.
# dotenv_values: reads APP_API_KEY from the project's .env file.
import argparse
import json
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

# --- Settings ----------------------------------------------------------------
EVAL_DIR = Path(__file__).parent
COMPANIES_DIR = EVAL_DIR / "companies"           # one folder per company id
RESULTS_DIR = EVAL_DIR / "results"
ENV = dotenv_values(EVAL_DIR.parent / ".env")      # project .env, read without changing os.environ

DEFAULT_URL = "http://127.0.0.1:8000"
NOT_FOUND_PHRASE = "could not find"                 # from the API's fixed not-found reply
DELAY_SECONDS = 1.0                                 # pause between questions


# --- Text matching ----------------------------------------------------------------------
def contains(text: str, needle: str) -> bool:
    """
    True if `needle` appears in `text`.
    - Numbers ("1,576.97", "13") must match as a whole number, with or without
      commas: "1576.97" counts, but "13" inside "2013" or "57.45" inside
      "157.45" does not.
    - Anything else is a simple case-insensitive substring match.
    """
    text, needle = text.lower(), needle.lower()
    if re.fullmatch(r"[\d.,]+", needle):
        number = needle.replace(",", "")
        flat_text = text.replace(",", "")
        return re.search(rf"(?<![\d.]){re.escape(number)}(?!\d)", flat_text) is not None
    return needle in text


def page_covers(pages: str, page: str) -> bool:
    """'11' covers '11'; a range like '6-7' covers both '6' and '7'."""
    first, _, last = str(pages).partition("-")
    return int(first) <= int(page) <= int(last or first)


# --- Grading one answer --------------------------------------------------------------------
def grade(case: dict, response: dict) -> list[str]:
    """Returns the list of failed checks. Empty list = PASS."""
    checks = case["checks"]
    answer = response.get("answer", "")
    pages = [source.get("pages", "") for source in response.get("sources", [])]
    failures = []

    # Refusal cases: must refuse, and must not sneak in a figure.
    if checks.get("expect_not_found"):
        if not contains(answer, NOT_FOUND_PHRASE):
            failures.append("should have said not found")

    # Every required fact: each group passes if ANY of its spellings is present.
    for group in checks.get("must_contain", []):
        if not any(contains(answer, option) for option in group):
            failures.append(f"missing {group[0]!r}")

    # Ambiguous cases: at least one valid interpretation must be fully present.
    if "accept_any_of" in checks:
        if not any(all(any(contains(answer, o) for o in g) for g in option["must_contain"])
                   for option in checks["accept_any_of"]):
            failures.append("matches none of the accepted interpretations")

    # Known wrong values.
    for wrong in checks.get("must_not_contain", []):
        if contains(answer, wrong):
            failures.append(f"contains wrong value {wrong!r}")

    # Citations must include a source on one of the expected pages.
    expected_pages = checks.get("expected_pages", [])
    if expected_pages and not any(page_covers(p, e) for p in pages if p for e in expected_pages):
        failures.append(f"no source on page(s) {','.join(expected_pages)} (got {pages or 'none'})")

    return failures


# --- Calling the API ------------------------------------------------------------------------
def ask(url: str, api_key: str, request: dict) -> dict:
    """POST one question to /ask and return the JSON reply."""
    req = urllib.request.Request(
        f"{url.rstrip('/')}/ask",
        data=json.dumps(request).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as reply:
        return json.loads(reply.read())


def self_test_response(case: dict) -> dict:
    """For --self-test: the case's own expected response, shaped like an /ask reply."""
    return case["expected_response"]


# --- One company's run --------------------------------------------------------------------
def run_company(company_id: str, eval_set: dict, args, api_key: str) -> tuple[int, int]:
    """Runs (or self-tests) one company's cases. Returns (passed, total)."""
    cases = eval_set["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if not cases:
        return 0, 0

    print(f"\n=== {company_id} - {len(cases)} case(s) ===")
    print(f"{'result':6} {'id':13} {'category':18} details")
    print("-" * 100)
    results = []
    for number, case in enumerate(cases):
        try:
            response = self_test_response(case) if args.self_test else ask(args.url, api_key, case["request"])
            failures = grade(case, response)
            status = "PASS" if not failures else "FAIL"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            response, failures, status = {}, [f"request failed: {error}"], "ERROR"

        judge_note = "  [needs judge]" if case.get("needs_judge") and status == "PASS" else ""
        print(f"{status:6} {case['id']:13} {case['category']:18} {'; '.join(failures)}{judge_note}")
        # One record per case: the verdict first, then expected vs actual side
        # by side, so the saved file can be read (or judged) on its own.
        results.append({
            "id": case["id"],
            "category": case["category"],
            "status": status,
            "failures": failures,
            "needs_judge": case.get("needs_judge", False),
            "judge_focus": case.get("judge_focus", ""),
            "request": case["request"],
            "expected_response": case["expected_response"],
            "actual_response": response,
            "checks": case["checks"],
            "source_note": case.get("source_note", ""),
        })
        if not args.self_test and number < len(cases) - 1:
            time.sleep(DELAY_SECONDS)

    # Score per category.
    by_category = defaultdict(lambda: [0, 0])
    for r in results:
        by_category[r["category"]][1] += 1
        by_category[r["category"]][0] += r["status"] == "PASS"
    passed = sum(r["status"] == "PASS" for r in results)
    print("-" * 100)
    for category, (ok, total) in sorted(by_category.items()):
        print(f"  {category:18} {ok}/{total}")
    print(f"{company_id}: {passed}/{len(results)} passed ({100 * passed / len(results):.0f}%)"
          f" - {sum(r['needs_judge'] and r['status'] == 'PASS' for r in results)} passes still need a judge review")

    # Save this company's run: summary at the top, then every case.
    if not args.self_test:
        out_dir = RESULTS_DIR / company_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.json"
        out.write_text(json.dumps({
            "company_id": company_id,
            "eval_set": eval_set.get("name", ""),
            "document": eval_set.get("document", {}),
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "api_url": args.url,
            "summary": {"passed": passed, "total": len(results),
                        "by_category": {c: f"{ok}/{total}" for c, (ok, total) in sorted(by_category.items())}},
            "cases": results,
        }, indent=2, ensure_ascii=False))
        print(f"Saved: {out}")
    return passed, len(results)


# --- Main ---------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the per-company eval sets against POST /ask")
    parser.add_argument("--url", default=DEFAULT_URL, help="API base URL")
    parser.add_argument("--company", action="append", help="company id folder, e.g. OFSS (repeatable; default: all)")
    parser.add_argument("--only", nargs="+", help="case ids to run, e.g. ofss-01 pl-01")
    parser.add_argument("--category", help="run only this category, e.g. prose_fact")
    parser.add_argument("--self-test", action="store_true", help="grade the expected answers (no API calls)")
    args = parser.parse_args()

    folders = sorted(p for p in COMPANIES_DIR.iterdir() if (p / "eval_set.json").exists())
    if args.company:
        wanted = {c.upper() for c in args.company}
        unknown = wanted - {p.name for p in folders}
        if unknown:
            parser.error(f"no eval set for {sorted(unknown)} - available: {[p.name for p in folders]}")
        folders = [p for p in folders if p.name in wanted]

    api_key = ENV.get("APP_API_KEY") or ""
    totals = {}
    for folder in folders:
        eval_set = json.loads((folder / "eval_set.json").read_text())
        passed, total = run_company(folder.name, eval_set, args, api_key)
        if total:
            totals[folder.name] = (passed, total)

    if len(totals) > 1:
        print("\n=== ALL COMPANIES ===")
        for company_id, (ok, total) in totals.items():
            print(f"  {company_id:10} {ok}/{total}")
        ok_all, total_all = sum(v[0] for v in totals.values()), sum(v[1] for v in totals.values())
        print(f"TOTAL {ok_all}/{total_all} passed ({100 * ok_all / max(total_all, 1):.0f}%)")


if __name__ == "__main__":
    main()
