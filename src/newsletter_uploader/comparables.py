"""Fresh comparables before a newsletter goes out.

Max, 2026-10-21: "even if we've already published something, we should do a
fresh comp review before big pushes like newsletters". Every policyengine.org
analysis an edition links must have a comparables search recorded in
PolicyEngine/policyengine-scorecard (docs/COMPARABLES.md there):

- dated on the push date or in the scorecard's promotion window before it
  (the window counts both ends: 7 days means the push date and the 7 days
  before it);
- against the results files the analysis reads now (the search's
  ``results_pins`` equal the record's ``current_pins``);
- with no gap found by the push date still pending.

The 20 October 2026 UK edition re-promoted the childcare dashboard at
£0.59bn; a fresh search would have found CenTax's £0.80bn static cost for the
30 hours alone. The check does not make an edition print the comparable.

What counts as an analysis is decided by policyengine-app-v2's registries and
the rules the scorecard's index publishes (``entry_rules``): an app listed
with research or tagged ``policy``, or any post, unless it is a post that is
plainly not an analysis (an event, an announcement) and declares
``no_estimate``. A link is recognised in any common form: with or without a
scheme or ``www.``, in any case, HTML-escaped or percent-encoded, through
``/research/`` or ``/blog/``, with a dated post slug, through one of the
site's redirects to an analysis (``ALIASES``), or to the app's own host.
Tracking links and link shorteners are refused, because where they lead
cannot be checked.

An edition is a file whose name starts with its date, ``YYYY-MM-DD``
(``editions/2026-11-02-uk.html``, ``editions/2026-11-02.html``, and the
``.md`` social posts beside them). ``upload-newsletter`` refuses an undated
file and judges freshness on the later of the edition's date and the day it
runs; CI checks the editions a change adds or modifies, on their dates. Only
pushes on or after ``PROMOTION_CUTOVER_DATE`` are checked. The registries and
the scorecard's index are downloaded from their repositories' main branches
only when an edition is due; a failed download, or an index of the wrong
shape, fails the check.

    python -m newsletter_uploader.comparables editions
    python -m newsletter_uploader.comparables --require-dates editions/<file>

``fresh`` is the scorecard's ``comparables.fresh``; both are tested against
``tests/fixtures/comparables_fresh_cases.json``, a copy of the scorecard's.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests

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
# The scorecard's policy keeps its window in this range too.
MAX_WINDOW_DAYS = 90

EDITION_SUFFIXES = (".html", ".htm", ".md")
_EDITION = re.compile(r"^(\d{4}-\d{2}-\d{2})(?=[-_.]|$)")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATED_SLUG = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")
_SITE = re.compile(
    r"(?<![a-z0-9.-])(?:https?:)?(?://)?(?:www\.)?policyengine\.org(?::\d+)?"
    r"((?:/+[a-z0-9_.~%-]*)*)",
    re.IGNORECASE,
)
_URL = re.compile(
    r"(?<![a-z0-9.@-])(?:https?:)?(?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})"
    r"(?::\d+)?(/[^\s\"'<>)\]]*)?",
    re.IGNORECASE,
)
_SEGMENT = re.compile(r"^[a-z0-9_-]+$")
# Links whose destination cannot be read from the link itself: Mailchimp's
# click tracking (its profile and unsubscribe links are fine) and shorteners.
TRACKING = (("list-manage.com", "/track/"),)
UNCHECKABLE_HOSTS = (
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "ow.ly",
    "buff.ly",
    "lnkd.in",
    "shorturl.at",
    "rebrand.ly",
    "cutt.ly",
)

# Redirects on policyengine.org that land on an analysis (policyengine-app-v2
# website/next.config.ts, redirects()). Each target must be a research entry
# in the registry the check downloads, or the check fails: the table is then
# stale.
ALIASES: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("us", "obbba-household-explorer"): ("us", "obbba-households"),
    ("us", "obbba-household-by-household"): ("us", "obbba-households"),
    ("us", "obbba-scatter"): ("us", "obbba-households"),
    ("us", "obba-household-explorer"): ("us", "obbba-households"),
    ("us", "ob3-households"): ("us", "obbba-households"),
    ("us", "research/obbba-household-explorer"): ("us", "obbba-households"),
    ("us", "research/obbba-household-by-household"): ("us", "obbba-households"),
    ("us", "aca-reforms-calculator"): ("us", "aca-calc"),
    ("us", "cliff-watch"): ("us", "cliffwatch"),
}

# A linked analysis: ("app", country, slug) or ("post", "", slug).
Key = Tuple[str, str, str]


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def is_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def edition_date(path: Path) -> Optional[str]:
    match = _EDITION.match(path.name)
    if not match or not is_date(match.group(1)):
        return None
    return match.group(1)


def post_slug(filename: str) -> str:
    """The website's post slug (policyengine-app-v2 postTransformers.ts)."""
    return filename[: filename.find(".")].lower().replace("_", "-")


def _decode(text: str) -> str:
    # HTML entities, then percent-encoding, twice over for a link that was
    # escaped both ways
    for _ in range(2):
        text = urllib.parse.unquote(html.unescape(text))
    return text


def _segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def _clean_slug(segment: str) -> Optional[str]:
    match = re.match(r"^[a-z0-9_-]+", segment.lower())
    if not match:
        return None
    slug = match.group(0).rstrip("-_").replace("_", "-")
    return slug or None


def site_paths(text: str) -> List[List[str]]:
    """The path segments of every policyengine.org link, lowercased, once each."""
    seen: List[List[str]] = []
    for match in _SITE.finditer(_decode(text)):
        segments = [s.lower() for s in _segments(match.group(1) or "")]
        if segments not in seen:
            seen.append(segments)
    return seen


def other_links(text: str) -> List[Tuple[str, str]]:
    """(host, path) of every link to another host, lowercased, once each."""
    seen: List[Tuple[str, str]] = []
    for match in _URL.finditer(_decode(text)):
        host = match.group(1).lower().rstrip(".")
        if host == "policyengine.org" or host.endswith(".policyengine.org"):
            continue
        link = (host, (match.group(2) or "/").split("?")[0].split("#")[0].lower())
        if link not in seen:
            seen.append(link)
    return seen


def _host(url: str) -> Tuple[str, str]:
    parsed = urllib.parse.urlsplit(url)
    return (parsed.hostname or "").lower(), (parsed.path or "/").rstrip(
        "/"
    ).lower() or "/"


class Registry:
    """The research entries in policyengine-app-v2's registries, under the
    rules the scorecard's index publishes."""

    def __init__(self, apps: Sequence[dict], posts: Sequence[dict], rules: dict):
        self.rules = rules
        countries = rules["country_tags"]
        self.countries = set(countries)
        self.entries: Dict[Key, dict] = {}
        self.hosts: Dict[str, List[Key]] = {}
        for app in apps:
            tags = app.get("tags") or []
            if not (app.get("slug") and app.get("countryId")):
                continue
            if not (app.get("displayWithResearch") or "policy" in tags):
                continue
            key: Key = ("app", app["countryId"], app["slug"])
            self.entries[key] = {
                "kind": "app",
                "countries": [app["countryId"]],
                "slug": app["slug"],
                "tags": tags,
                "comparables": app.get("comparables"),
            }
            source = app.get("source") or ""
            host, _ = _host(source)
            if host.endswith(".vercel.app") or host.endswith(".github.io"):
                self.hosts.setdefault(host, []).append(key)
        for post in posts:
            tags = post.get("tags") or []
            slug = post_slug(post["filename"])
            self.entries[("post", "", slug)] = {
                "kind": "post",
                "countries": [t for t in tags if t in self.countries]
                or [rules["default_country"]],
                "slug": slug,
                "tags": tags,
                "comparables": post.get("comparables"),
            }

    def stale_aliases(self) -> List[str]:
        return [
            f"{c}/{path} -> {tc}/{ts}"
            for (c, path), (tc, ts) in ALIASES.items()
            if ("app", tc, ts) not in self.entries
        ]

    def from_path(self, segments: List[str]) -> Tuple[Optional[Key], Optional[str]]:
        """The entry a policyengine.org path names, or why none is known."""
        if len(segments) < 2 or segments[0] not in self.countries:
            return None, None
        country = segments[0]
        if segments[1] in ("research", "blog"):
            slug = _clean_slug(segments[2]) if len(segments) > 2 else None
            if slug is None:
                return None, None
            alias = ALIASES.get((country, f"research/{slug}"))
            if alias:
                return ("app",) + alias, None
            if ("post", "", slug) in self.entries:
                return ("post", "", slug), None
            dated = _DATED_SLUG.match(slug)
            if dated and ("post", "", dated.group(1)) in self.entries:
                return ("post", "", dated.group(1)), None
            return None, f"policyengine.org/{country}/research/{slug} is not a post"
        slug = _clean_slug(segments[1])
        alias = ALIASES.get((country, slug or ""))
        if alias:
            return ("app",) + alias, None
        if slug and ("app", country, slug) in self.entries:
            return ("app", country, slug), None
        return None, None

    def from_host(self, host: str) -> List[Key]:
        """The research apps served from a host: the host in an app's source,
        or one of its Vercel preview deployments (<project>-git-<branch>-...)."""
        if host in self.hosts:
            return self.hosts[host]
        for known, keys in self.hosts.items():
            project = known.split(".")[0]
            if host.endswith(".vercel.app") and host.startswith(f"{project}-git-"):
                return keys
        return []

    def may_declare_no_estimate(self, entry: dict) -> bool:
        tags = set(entry["tags"])
        return (
            entry["kind"] == "post"
            and bool(tags & set(self.rules["no_estimate_tags"]))
            and not tags & set(self.rules["analysis_tags"])
        )

    def publishes_estimate(self, entry: dict) -> bool:
        record = entry.get("comparables") or {}
        return not (
            isinstance(record, dict)
            and record.get("status") == "no_estimate"
            and self.may_declare_no_estimate(entry)
        )


def linked_analyses(text: str, registry: Registry) -> Tuple[List[Key], List[str]]:
    """Every research entry an edition links, and every link the check refuses."""
    keys: List[Key] = []
    refused: List[str] = []
    for segments in site_paths(text):
        key, problem = registry.from_path(segments)
        if problem:
            refused.append(problem)
        if key and key not in keys:
            keys.append(key)
    for host, path in other_links(text):
        tracked = any(
            (host == h or host.endswith(f".{h}")) and path.startswith(prefix)
            for h, prefix in TRACKING
        )
        if tracked or any(
            host == h or host.endswith(f".{h}") for h in UNCHECKABLE_HOSTS
        ):
            refused.append(
                f"{host}{path} hides where it leads (a tracking link or a shortener); "
                "link the policyengine.org page itself"
            )
            continue
        for key in registry.from_host(host):
            if key not in keys:
                keys.append(key)
    return keys, refused


def fresh(index_entry: dict, on: str, window_days: int) -> List[str]:
    """Why an analysis may not be promoted on ``on``: the scorecard's
    ``comparables.fresh``. A pending gap with no ``found_on`` counts as
    found."""
    start = (dt.date.fromisoformat(on) - dt.timedelta(days=window_days)).isoformat()
    reasons = []
    pins = sorted(index_entry.get("current_pins") or [])
    searches = index_entry["searches"]
    recent = [s for s in searches if start <= s["date"] <= on]
    if not recent:
        earlier = [s["date"] for s in searches if s["date"] <= on]
        last = max(earlier) if earlier else "none"
        reasons.append(
            f"no comparables search between {start} and {on} (last: {last}); "
            "run a prepromotion search before sending"
        )
    elif not any(sorted(s.get("results_pins") or []) == pins for s in recent):
        reasons.append(
            f"no search between {start} and {on} compared the results the page reads "
            "now; run a prepromotion search against them"
        )
    pending = [
        c["claim"]
        for c in index_entry.get("comparisons", [])
        if c.get("status") == "pending" and (c.get("found_on") or "") <= on
    ]
    if pending:
        reasons.append(
            f"gaps still pending by {on}: {', '.join(pending)}; "
            "explain them before sending"
        )
    return reasons


def check_index(index: object) -> List[str]:
    """Every reason the downloaded index cannot be trusted."""
    if not isinstance(index, dict):
        return ["the scorecard index is not a JSON object"]
    errors = []
    if index.get("schema") != INDEX_SCHEMA:
        errors.append(
            f"the scorecard index schema is {index.get('schema')!r}, not {INDEX_SCHEMA}"
        )
    window = index.get("promotion_window_days")
    if (
        not isinstance(window, int)
        or isinstance(window, bool)
        or not 1 <= window <= MAX_WINDOW_DAYS
    ):
        errors.append(
            f"the scorecard index's promotion_window_days is {window!r}, "
            f"not a whole number of days from 1 to {MAX_WINDOW_DAYS}"
        )
    rules = index.get("entry_rules")
    if (
        not isinstance(rules, dict)
        or not all(
            isinstance(rules.get(k), list)
            for k in ("analysis_tags", "no_estimate_tags", "country_tags")
        )
        or not isinstance(rules.get("default_country"), str)
    ):
        errors.append("the scorecard index publishes no entry_rules")
    analyses = index.get("analyses")
    if not isinstance(analyses, dict):
        return errors + ["the scorecard index has no analyses object"]
    for source, entry in analyses.items():
        where = f"the scorecard index's {source}"
        if not isinstance(entry, dict):
            errors.append(f"{where} is not an object")
            continue
        searches = entry.get("searches")
        if not isinstance(searches, list) or not searches:
            errors.append(f"{where} lists no searches")
        else:
            for s in searches:
                if not isinstance(s, dict) or not is_date(s.get("date")):
                    errors.append(f"{where} has a search with no real date")
                elif not isinstance(s.get("results_pins"), list):
                    errors.append(f"{where} has a search with no results_pins")
        if not isinstance(entry.get("current_pins"), list):
            errors.append(f"{where} has no current_pins")
        comparisons = entry.get("comparisons", [])
        if not isinstance(comparisons, list) or not all(
            isinstance(c, dict) and isinstance(c.get("status"), str)
            for c in comparisons
        ):
            errors.append(f"{where} has a comparison with no status")
    return errors


def record_for(
    key: Key, entry: dict, index: dict
) -> Tuple[Optional[str], Optional[dict]]:
    """The scorecard record an entry names, or the one its name implies."""
    analyses = index["analyses"]
    block = entry.get("comparables")
    if isinstance(block, dict) and isinstance(block.get("scorecardSource"), str):
        candidates = [block["scorecardSource"]]
    else:
        candidates = [f"analysis-{c}-{entry['slug']}" for c in entry["countries"]]
    for source in candidates:
        recorded = analyses.get(source)
        if (
            recorded
            and recorded.get("kind") == entry["kind"]
            and recorded.get("slug") == entry["slug"]
        ):
            return source, recorded
    return candidates[0], None


def _page(key: Key) -> str:
    kind, country, slug = key
    return (
        f"policyengine.org/{country}/{slug}"
        if kind == "app"
        else f"policyengine.org/research/{slug}"
    )


def check_edition(
    name: str, text: str, on: str, registry: Registry, index: dict
) -> List[str]:
    """Every reason this edition may not go out on ``on``."""
    window = index["promotion_window_days"]
    keys, refused = linked_analyses(text, registry)
    errors = [f"{name}: {problem}" for problem in refused]
    for key in keys:
        entry = registry.entries[key]
        if not registry.publishes_estimate(entry):
            continue
        source, recorded = record_for(key, entry, index)
        if recorded is None:
            errors.append(
                f"{name}: {_page(key)} has no comparables record in the scorecard; "
                f"run the comparables review ({source}) before sending"
            )
            continue
        for reason in fresh(recorded, on, window):
            errors.append(f"{name}: {_page(key)}: {reason}")
    # A page the registry no longer lists (taken down, or not yet listed)
    # that still has a scorecard record is held to its record.
    for segments in site_paths(text):
        if len(segments) < 2 or segments[0] not in registry.countries:
            continue
        slug = _clean_slug(segments[1])
        source = f"analysis-{segments[0]}-{slug}"
        recorded = index["analyses"].get(source)
        if (
            slug is None
            or ("app", segments[0], slug) in keys
            or recorded is None
            or recorded.get("kind") != "app"
        ):
            continue
        page = f"policyengine.org/{segments[0]}/{slug}"
        for reason in fresh(recorded, on, window):
            errors.append(f"{name}: {page}: {reason}")
    return errors


def edition_files(paths: Sequence[Path]) -> List[Path]:
    """The files named, and every edition-like file under a directory named."""
    files: List[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                p
                for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in EDITION_SUFFIXES
            )
        else:
            files.append(path)
    return files


def due_editions(
    files: Sequence[Path], cutover: str, today: Optional[str], require_dates: bool
) -> Tuple[List[Tuple[Path, str]], List[str]]:
    """Each edition to check with the date to judge it on, and every file
    that cannot be dated. The date is the edition's, or today when that is
    later (an upload after the edition's date)."""
    due: List[Tuple[Path, str]] = []
    errors: List[str] = []
    for path in files:
        date = edition_date(path)
        if date is None:
            if require_dates:
                errors.append(
                    f"{path.name}: no YYYY-MM-DD date at the start of the file name, "
                    "so its comparables cannot be checked; name it <date>-<audience>"
                )
            continue
        on = max(date, today) if today else date
        if on >= cutover:
            due.append((path, on))
    return due, errors


def _load(where: str) -> object:
    if not where.startswith("https://"):
        return json.loads(Path(where).read_text(encoding="utf-8"))
    last_error: Optional[Exception] = None
    for attempt in range(4):
        try:
            response = requests.get(where, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as error:  # noqa: BLE001 - every failure retries, then fails
            last_error = error
            time.sleep(2**attempt)
    raise SystemExit(f"could not read {where}: {last_error}")


def run_check(
    files: Sequence[Path],
    apps: Optional[str] = None,
    posts: Optional[str] = None,
    index_source: Optional[str] = None,
    cutover: Optional[str] = None,
    today: Optional[str] = None,
    require_dates: bool = False,
) -> Tuple[List[Path], List[str]]:
    """Check every edition due on or after the cutover. The sources and the
    cutover default to the module's ``APPS_URL``, ``POSTS_URL``,
    ``INDEX_URL`` and ``PROMOTION_CUTOVER_DATE``, read when called. Returns
    the editions checked and every error; downloads nothing when none is
    due."""
    apps = apps or APPS_URL
    posts = posts or POSTS_URL
    index_source = index_source or INDEX_URL
    due, errors = due_editions(
        files, cutover or PROMOTION_CUTOVER_DATE, today, require_dates
    )
    if not due:
        return [], errors
    index = _load(index_source)
    problems = check_index(index)
    if problems:
        return [path for path, _ in due], errors + problems
    registry = Registry(_load(apps), _load(posts), index["entry_rules"])
    stale = registry.stale_aliases()
    if stale:
        return [path for path, _ in due], errors + [
            "the redirect table in comparables.py names an analysis the "
            f"registry no longer lists: {a}"
            for a in stale
        ]
    for path, on in due:
        text = path.read_text(encoding="utf-8")
        errors.extend(check_edition(path.name, text, on, registry, index))
    return [path for path, _ in due], errors


HOW_TO_FIX = (
    "Run the comparables review for each analysis above (the "
    "policyengine-comparables-review skill, search kind prepromotion), merge its "
    "scorecard PR, then check again; raw.githubusercontent.com caches the index "
    "for up to 5 minutes after a merge."
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m newsletter_uploader.comparables")
    parser.add_argument("paths", nargs="*", default=["editions"])
    parser.add_argument("--apps", default=None)
    parser.add_argument("--posts", default=None)
    parser.add_argument("--index", default=None)
    parser.add_argument("--cutover", default=None)
    parser.add_argument(
        "--require-dates",
        action="store_true",
        help="fail a file whose name does not start with its date",
    )
    args = parser.parse_args(argv)

    files = edition_files([Path(raw) for raw in args.paths])
    due, errors = run_check(
        files,
        args.apps,
        args.posts,
        args.index,
        args.cutover,
        require_dates=args.require_dates,
    )
    cutover = args.cutover or PROMOTION_CUTOVER_DATE
    if not due and not errors:
        print(f"No edition dated on or after {cutover}; nothing to check.")
        return 0
    file_errors = {
        path.name for path in due if any(e.startswith(f"{path.name}:") for e in errors)
    }
    general = [e for e in errors if not any(e.startswith(f"{p.name}:") for p in files)]
    if not general:
        for path in due:
            print(f"{'FAIL' if path.name in file_errors else 'ok  '} {path.name}")
    for error in errors:
        print(f"  {error}")
    if errors:
        print("\n" + HOW_TO_FIX)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
