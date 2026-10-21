"""Fresh comparables before a newsletter goes out.

Max, 2026-10-21: "even if we've already published something, we should do a
fresh comp review before big pushes like newsletters". Every policyengine.org
analysis an edition links must have a comparables search recorded in
PolicyEngine/policyengine-scorecard (docs/COMPARABLES.md there) dated within
the scorecard's promotion window before the edition's date, and no gap found
by then still unexplained. The 21 October 2026 UK edition re-promoted the
childcare dashboard at £0.59bn; a fresh search would have put CenTax's £0.80bn
static cost for the 30 hours alone beside it.

What counts as an analysis is decided by policyengine-app-v2's registries: an
app listed with research, or a post, that publishes an estimate (tagged
``policy``, or carrying a reviewed comparables block) and has not declared
``no_estimate``. Links to anything else (the home page, calculators, the
research index) are not checked.

Editions are ``editions/<YYYY-MM-DD>-<audience>.html`` (and the ``.md`` social
posts beside them). Only editions dated on or after ``PROMOTION_CUTOVER_DATE``
are checked, so the archive never changes its verdict. The registries and the
scorecard's index are downloaded from their repositories' main branches only
when such an edition exists; a failed download fails the check.

    python -m newsletter_uploader.comparables editions
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PROMOTION_CUTOVER_DATE = "2026-10-26"

APPS_URL = (
    "https://raw.githubusercontent.com/PolicyEngine/policyengine-app-v2/main/"
    "app/src/data/apps/apps.json"
)
POSTS_URL = (
    "https://raw.githubusercontent.com/PolicyEngine/policyengine-app-v2/main/"
    "app/src/data/posts/posts.json"
)
INDEX_URL = (
    "https://raw.githubusercontent.com/PolicyEngine/policyengine-scorecard/main/"
    "data/comparables/index.json"
)
INDEX_SCHEMA = "comparables/index/1"

COUNTRIES = ("uk", "us", "ca", "ng", "il")
_LINK = re.compile(
    r"https?://(?:www\.)?policyengine\.org/(uk|us|ca|ng|il)/(research/)?"
    r"([A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*)(?=[/?#\"'\s<>)\].,;:!]|$)"
)
_EDITION = re.compile(r"^(\d{4}-\d{2}-\d{2})-")

Key = Tuple[str, str, str]  # (country, "app" | "post", slug)


def edition_date(path: Path) -> Optional[str]:
    match = _EDITION.match(path.name)
    if not match:
        return None
    try:
        dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return match.group(1)


def post_slug(filename: str) -> str:
    """The website's post slug (policyengine-app-v2 postTransformers.ts)."""
    stem = filename[: filename.index(".")] if "." in filename else filename
    return stem.lower().replace("_", "-")


def analysis_links(text: str) -> List[Key]:
    """Every policyengine.org country page an edition links, once each."""
    seen: List[Key] = []
    for country, research, slug in _LINK.findall(text):
        key = (
            country.lower(),
            "post" if research else "app",
            slug.lower().replace("_", "-"),
        )
        if key not in seen:
            seen.append(key)
    return seen


def research_entries(apps: Sequence[dict], posts: Sequence[dict]) -> Dict[Key, dict]:
    entries: Dict[Key, dict] = {}
    for app in apps:
        if app.get("displayWithResearch") and app.get("slug") and app.get("countryId"):
            entries[(app["countryId"], "app", app["slug"])] = app
    for post in posts:
        for tag in post.get("tags", []):
            if tag in COUNTRIES:
                entries[(tag, "post", post_slug(post["filename"]))] = post
    return entries


def publishes_estimate(entry: dict) -> bool:
    record = entry.get("comparables") or {}
    if record.get("status") == "no_estimate":
        return False
    return "policy" in entry.get("tags", []) or record.get("status") == "reviewed"


def fresh(index_entry: dict, on: str, window_days: int) -> List[str]:
    """Why an analysis may not be promoted on ``on``: the same rule as the
    scorecard's ``comparables.fresh``."""
    start = (dt.date.fromisoformat(on) - dt.timedelta(days=window_days)).isoformat()
    reasons = []
    searches = index_entry.get("searches", [])
    if not any(start <= s["date"] <= on for s in searches):
        earlier = [s["date"] for s in searches if s["date"] <= on]
        last = max(earlier) if earlier else "none"
        reasons.append(
            f"no comparables search between {start} and {on} (last: {last}); "
            "run a prepromotion search before sending"
        )
    pending = [
        c["claim"]
        for c in index_entry.get("comparisons", [])
        if c.get("status") == "pending" and c.get("found_on", "9999") <= on
    ]
    if pending:
        reasons.append(
            f"gaps still pending by {on}: {', '.join(pending)}; "
            "explain them before sending"
        )
    return reasons


def check_edition(
    path: Path,
    text: str,
    entries: Dict[Key, dict],
    index: dict,
) -> List[str]:
    """Every reason this edition may not go out."""
    on = edition_date(path)
    if on is None:
        return [f"{path.name}: no YYYY-MM-DD date at the start of the file name"]
    window = index["promotion_window_days"]
    errors = []
    for country, kind, slug in analysis_links(text):
        entry = entries.get((country, kind, slug))
        if entry is None or not publishes_estimate(entry):
            continue
        source = f"analysis-{country}-{slug}"
        page = (
            f"policyengine.org/{country}/{'research/' if kind == 'post' else ''}{slug}"
        )
        recorded = index["analyses"].get(source)
        if recorded is None or recorded.get("kind") != kind:
            errors.append(
                f"{path.name}: {page} has no comparables record in the scorecard; "
                f"run the comparables review ({source}) before sending"
            )
            continue
        for reason in fresh(recorded, on, window):
            errors.append(f"{path.name}: {page}: {reason}")
    return errors


def editions_to_check(paths: Sequence[Path], cutover: str) -> List[Path]:
    out = []
    for path in sorted(paths):
        date = edition_date(path)
        if date is not None and date >= cutover:
            out.append(path)
    return out


def _load(where: str) -> object:
    if not where.startswith("https://"):
        return json.loads(Path(where).read_text())
    last_error: Optional[Exception] = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(where, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - every failure retries, then fails
            last_error = error
            time.sleep(2**attempt)
    raise SystemExit(f"could not read {where}: {last_error}")


def run_check(
    files: Sequence[Path],
    apps: str = APPS_URL,
    posts: str = POSTS_URL,
    index_source: str = INDEX_URL,
    cutover: Optional[str] = None,
) -> Tuple[List[Path], List[str]]:
    """Check every edition dated on or after the cutover (the module's
    ``PROMOTION_CUTOVER_DATE`` unless given). Returns the editions checked and
    every error; downloads nothing when none is due."""
    due = editions_to_check(files, cutover or PROMOTION_CUTOVER_DATE)
    if not due:
        return [], []
    index = _load(index_source)
    if not isinstance(index, dict) or index.get("schema") != INDEX_SCHEMA:
        return due, [f"the scorecard index at {index_source} is not {INDEX_SCHEMA}"]
    entries = research_entries(_load(apps), _load(posts))
    errors: List[str] = []
    for path in due:
        errors.extend(check_edition(path, path.read_text(), entries, index))
    return due, errors


HOW_TO_FIX = (
    "Run the comparables review for each analysis above (the "
    "policyengine-comparables-review skill, search kind prepromotion), merge its "
    "scorecard PR, then check again."
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m newsletter_uploader.comparables")
    parser.add_argument("paths", nargs="*", default=["editions"])
    parser.add_argument("--apps", default=APPS_URL)
    parser.add_argument("--posts", default=POSTS_URL)
    parser.add_argument("--index", default=INDEX_URL)
    parser.add_argument("--cutover", default=None)
    args = parser.parse_args(argv)

    files: List[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(p for p in path.iterdir() if p.suffix in (".html", ".md"))
        else:
            files.append(path)
    due, errors = run_check(files, args.apps, args.posts, args.index, args.cutover)
    if not due:
        cutover = args.cutover or PROMOTION_CUTOVER_DATE
        print(f"No edition dated on or after {cutover}; nothing to check.")
        return 0
    for path in due:
        failed = any(e.startswith(f"{path.name}:") for e in errors)
        print(f"{'FAIL' if failed else 'ok  '} {path.name}")
    for error in errors:
        print(f"  {error}")
    if errors:
        print("\n" + HOW_TO_FIX)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
