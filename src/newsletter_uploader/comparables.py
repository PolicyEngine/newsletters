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
``no_estimate``. Where a link leads is read from policyengine-app-v2's route
map (``website/src/data/analysisRoutes.json``: every path, redirect and
deployment host that leads to a research app, built from the site's own
routing) and from the scorecard's records (each analysis's page and the
``deployments`` it is also served from, which keep a dashboard taken off the
site from being promoted through its own URL). For a shared deployment, the
pinned registry's source URLs narrow the map's candidates by path and country
query, including the default country. Ambiguous destinations are refused.
A link is recognised in any
common form: with or without a scheme or ``www.``, in any case, HTML-escaped
or percent-encoded, with dot segments or a trailing dot on the host, through
``/research/`` or ``/blog/`` or a dated post slug. Tracking links and link
shorteners are refused, because where they lead cannot be checked.

An edition is a file whose name starts with its date, ``YYYY-MM-DD``
(``editions/2026-11-02-uk.html``, ``editions/2026-11-02.html``, and the
``.md`` social posts beside them, ``editions/<date>-<audience>-social.md``).
``upload-newsletter`` refuses an undated file and judges freshness on the
later of the edition's date and the day it runs; CI checks the editions a
change adds or modifies, on their dates. Only pushes on or after
``PROMOTION_CUTOVER_DATE`` are checked. The registries, the route map and the
scorecard's index are read from their repositories' main branches, at the
commit main points to when the check runs (so a cached copy is never read),
only when an edition is due; a failed download, or data of the wrong shape,
fails the check.

    python -m newsletter_uploader.comparables editions
    python -m newsletter_uploader.comparables --require-dates editions/<file>

``fresh`` is the scorecard's ``comparables.fresh``; both are tested against
``tests/fixtures/comparables_fresh_cases.json``, a copy of the scorecard's.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import ipaddress
import json
import os
import posixpath
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import requests

from .hosting_links import ATTRIBUTE, URL_ATTRIBUTES

PROMOTION_CUTOVER_DATE = "2026-10-26"

APP_V2 = "PolicyEngine/policyengine-app-v2"
SCORECARD = "PolicyEngine/policyengine-scorecard"
APPS_URL = (
    f"https://raw.githubusercontent.com/{APP_V2}/main/app/src/data/apps/apps.json"
)
POSTS_URL = (
    f"https://raw.githubusercontent.com/{APP_V2}/main/app/src/data/posts/posts.json"
)
ROUTES_URL = (
    f"https://raw.githubusercontent.com/{APP_V2}/main/"
    "website/src/data/analysisRoutes.json"
)
INDEX_URL = (
    f"https://raw.githubusercontent.com/{SCORECARD}/main/data/comparables/index.json"
)
INDEX_SCHEMA = "comparables/index/1"
ROUTES_SCHEMA = "analysis-routes/1"
# The scorecard's policy keeps its window in this range too.
MAX_WINDOW_DAYS = 90
STATUSES = ("comparable", "constructed", "concept_mismatch", "pe_gap", "pending")

EDITION_SUFFIXES = (".html", ".htm", ".md")
SITE_HOST = "policyengine.org"
_EDITION = re.compile(r"^(\d{4}-\d{2}-\d{2})(?=[-_.]|$)")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATED_SLUG = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)$")
# Complete absolute links must be parsed before scanning bare domains: userinfo
# and backslashes affect their browser destination, rather than ending a link.
_ABSOLUTE_LINK = re.compile(
    r"(?:https?(?::|%(?:25){0,2}3a)[^\s<>\"']+|//[^\s<>\"']+)",
    re.IGNORECASE,
)
_LINK = re.compile(
    r"(?<![a-z0-9@.-])((?:[a-z0-9-]+\.)+[a-z]{2,}\.?)"
    r"(?::\d+)?(?:[/\\?][^\s<>\"']*)?",
    re.IGNORECASE,
)
_RAW_MAIN = re.compile(r"^https://raw\.githubusercontent\.com/([^/]+/[^/]+)/main/(.+)$")
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

# What a link leads to: a research entry, ("app", country, slug) or ("post",
# "", slug), or a scorecard record whose analysis the registries no longer list.
Key = Tuple[str, str, str]
Target = Tuple[str, object]  # ("entry", Key) or ("record", source)


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


def normalize_host(host: str) -> str:
    host = host.encode("idna").decode("ascii").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def normalize_path(path: str) -> str:
    """A path as the site routes it: lowercase, underscores as hyphens,
    repeated slashes and dot segments resolved, trailing punctuation and
    slash dropped."""
    path = re.sub(r"/+", "/", "/" + (path or "").lower())
    path = posixpath.normpath(path)
    segments = [s.strip(".-_").replace("_", "-") for s in path.split("/")]
    path = "/".join(s for s in segments if s)
    return f"/{path}" if path else "/"


def _link_url(url: str) -> Tuple[str, str, str]:
    """Parse the browser destination of an HTTP(S) URL, preserving its query.

    Browsers treat backslashes before the query as slashes for these schemes.
    urllib alone does not, so apply that rule before parsing its authority.
    """
    url = html.unescape(url).strip().rstrip(".,;:!?)\u2014\u2019|*")
    # Unwrap an encoded whole URL only until its structural delimiters are
    # visible. Decoding a normal URL before splitting turns encoded ? or #
    # inside its path into a false query or fragment boundary.
    for _ in range(3):
        if re.match(r"^(?:https?:|//)", url, re.IGNORECASE):
            break
        decoded = urllib.parse.unquote(url)
        if decoded == url:
            break
        url = decoded
    before_query, separator, query = url.partition("?")
    url = before_query.replace("\\", "/") + separator + query
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError("an absolute HTTP(S) URL needs a hostname")
        host = parsed.hostname
        parsed.port  # Reject invalid ports instead of losing a destination.
        if not host or any(c.isspace() for c in host):
            raise ValueError("the hostname is missing or invalid")
        host = normalize_host(_decode(host))
        if not _valid_hostname(host):
            raise ValueError("the hostname is invalid")
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"unsupported absolute link {url!r}: {exc}") from exc
    # Keep the complete path through dot-segment resolution, including Unicode
    # segments. Truncating at an unfamiliar character can hide the destination
    # of a later /../ segment.
    path = normalize_path(_decode(parsed.path))
    # Some newsletter prose appends tracking fields without a question mark.
    # Read that suffix only after resolving the complete browser path.
    path = re.sub(r"&[a-z_][a-z0-9_-]*=.*$", "", path)
    return host, path, parsed.query


def links(text: str) -> List[Tuple[str, str, str]]:
    """Normalised (host, path, query) links, once each.

    Unsupported absolute URLs raise ValueError so the edition fails closed.
    """
    seen: List[Tuple[str, str, str]] = []
    # Read complete URL attribute values before decoding percent-escapes.
    # Encoded whitespace or quotes must not split a path before a later /../.
    for attribute in ATTRIBUTE.finditer(text):
        name, _, double, single, bare = attribute.groups()
        if name.lower() not in URL_ATTRIBUTES:
            continue
        raw = next(value for value in (double, single, bare) if value is not None)
        value = re.sub("[\t\n\r]", "", html.unescape(raw)).strip()
        if re.match(r"^(?:https?(?::|%(?:25){0,2}3a)|//)", value, re.IGNORECASE):
            link = _link_url(value)
            if link not in seen:
                seen.append(link)
    text = html.unescape(text)
    consumed: List[Tuple[int, int]] = []
    for match in _ABSOLUTE_LINK.finditer(text):
        consumed.append(match.span())
        link = _link_url(match.group(0))
        if link not in seen:
            seen.append(link)
    for match in _LINK.finditer(text):
        if any(start <= match.start() < end for start, end in consumed):
            continue
        link = _link_url("https://" + match.group(0))
        if link not in seen:
            seen.append(link)
    return seen


def _host_path(url: str) -> Tuple[str, str]:
    host, path, _ = _link_url(url)
    return host, path


def _under(path: str, prefix: str) -> bool:
    return prefix == "/" or path == prefix or path.startswith(prefix + "/")


class Registry:
    """The research entries in policyengine-app-v2's registries, under the
    rules the scorecard's index publishes."""

    def __init__(self, apps: Sequence[dict], posts: Sequence[dict], rules: dict):
        self.rules = rules
        self.countries = set(rules["country_tags"])
        self.entries: Dict[Key, dict] = {}
        for app in apps:
            tags = app.get("tags") or []
            if not (app.get("slug") and app.get("countryId")):
                continue
            if not (app.get("displayWithResearch") or "policy" in tags):
                continue
            self.entries[("app", app["countryId"], app["slug"])] = {
                "kind": "app",
                "countries": [app["countryId"]],
                "slug": app["slug"],
                "tags": tags,
                "comparables": app.get("comparables"),
                "source": app.get("source"),
            }
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


class Routes:
    """Where links lead: the route map supplies app membership; registry
    sources disambiguate shared deployments; scorecard pages retain delisted
    analyses. A shared host never implies ownership of every path on it.
    """

    def __init__(self, routes: dict, registry: Registry, index: dict):
        self.registry = registry
        self.index = index
        self.paths: List[Tuple[str, bool, Target]] = []
        self.hosts: List[Tuple[str, str, bool, List[Target]]] = []
        self.sources: Dict[str, List[str]] = {}
        owners: Dict[str, Set[str]] = {}
        bindings: List[Tuple[str, str, List[Target], bool]] = []
        for key, research in registry.entries.items():
            source = research.get("source")
            if isinstance(source, str) and source.startswith(("http://", "https://")):
                self.sources.setdefault(self._identity(("entry", key)), []).append(
                    source
                )
        for route in routes["paths"]:
            key = self._entry(route["entry"])
            if key:
                self.paths.append((route["path"], route["prefix"], ("entry", key)))
        for route in routes["hosts"]:
            keys = [k for k in (self._entry(e) for e in route["entries"]) if k]
            if keys:
                bindings.append(
                    (
                        route["host"],
                        route["pathPrefix"],
                        [("entry", k) for k in keys],
                        True,
                    )
                )
        # Primary pages and additional deployments use the same registration
        # path, including a standalone primary page with no deployments.
        for source, record in index["analyses"].items():
            target: Target = ("record", source)
            urls = [record["url"], *record.get("deployments", [])]
            self.sources.setdefault(source, []).extend(urls)
            for url in urls:
                host, path = _host_path(url)
                if host == SITE_HOST:
                    if path != "/":
                        self.paths.append((path, True, target))
                else:
                    bindings.append((host, path, [target], False))
        for host, _, targets, _ in bindings:
            owners.setdefault(host, set()).update(self._identity(t) for t in targets)
        for host, prefix, targets, from_map in bindings:
            shared = len(owners[host]) > 1
            for target in targets:
                boundary = prefix
                if shared and from_map and prefix == "/":
                    # The map's broad host ownership becomes unsafe when a
                    # second source identifies another analysis on that host.
                    # Its pinned registry source supplies a narrower boundary.
                    paths = [p for _, p, _ in self._source_links(target, host)]
                    nonroot = [p for p in paths if p != "/"]
                    if nonroot:
                        for path in nonroot:
                            self.hosts.append((host, path, True, [target]))
                        continue
                if host.endswith(".github.io") and boundary != "/":
                    boundary = "/" + boundary.split("/")[1]
                elif not shared and not from_map and not host.endswith(".github.io"):
                    boundary = "/"
                self.hosts.append(
                    (host, boundary, not (shared and boundary == "/"), [target])
                )

    def _identity(self, target: Target) -> str:
        if target[0] == "record":
            return str(target[1])
        return record_for(self.registry.entries[target[1]], self.index)[0]

    def _source_links(self, target: Target, host: str) -> List[Tuple[str, str, str]]:
        result = []
        for source in self.sources.get(self._identity(target), []):
            link = _link_url(source)
            if link[0] == host:
                result.append(link)
        return result

    def _entry(self, key: str) -> Optional[Key]:
        match = re.match(r"^app ([a-z]{2})/([a-z0-9-]+)$", key)
        if not match:
            return None
        entry = ("app", match.group(1), match.group(2))
        return entry if entry in self.registry.entries else None

    def on_site(self, path: str) -> Tuple[List[Target], Optional[str]]:
        """What a policyengine.org path leads to, or why it is refused."""
        segments = [s for s in path.split("/") if s]
        if (
            len(segments) >= 3
            and segments[0] in self.registry.countries
            and segments[1] in ("research", "blog")
        ):
            slug = segments[2]
            for candidate in (slug, (_DATED_SLUG.match(slug) or [None, None])[1]):
                if candidate and ("post", "", candidate) in self.registry.entries:
                    return [("entry", ("post", "", candidate))], None
        found: List[Target] = []
        for route_path, prefix, target in self.paths:
            if path == route_path or (prefix and path.startswith(route_path + "/")):
                if target not in found:
                    found.append(target)
        if found:
            return found, None
        if len(segments) >= 3 and segments[1] in ("research", "blog"):
            return [], f"policyengine.org{path} is not a post"
        return [], None

    def _country(self, target: Target) -> Optional[str]:
        if target[0] == "entry":
            countries = self.registry.entries[target[1]]["countries"]
            return countries[0] if len(countries) == 1 else None
        record = self.index["analyses"][target[1]]
        _, path = _host_path(record["url"])
        country = path.split("/")[1] if path != "/" else ""
        return country if country in self.registry.countries else None

    def off_site(self, host: str, path: str, query: str = "") -> List[Target]:
        """Resolve a deployment, refusing ambiguous country/default routing."""
        matches: List[Tuple[int, Target, str]] = []
        for route_host, prefix, subtree, targets in self.hosts:
            preview = (
                route_host.endswith(".vercel.app")
                and host.endswith(".vercel.app")
                and host.startswith(route_host.split(".")[0] + "-git-")
            )
            if (host == route_host or preview) and (
                path == prefix or (subtree and _under(path, prefix))
            ):
                matches.extend((len(prefix), target, route_host) for target in targets)
        if not matches:
            return []
        # An explicit nested project path takes precedence over its parent.
        most_specific = max(m[0] for m in matches)
        candidates = [(t, h) for length, t, h in matches if length == most_specific]
        identities = {self._identity(t) for t, _ in candidates}
        if len(identities) > 1:
            requested = urllib.parse.parse_qs(query, keep_blank_values=True).get(
                "country"
            )
            source_countries: Dict[str, Set[Optional[str]]] = {}
            explicit = False
            for target, route_host in candidates:
                identity = self._identity(target)
                countries = source_countries.setdefault(identity, set())
                for _, source_path, source_query in self._source_links(
                    target, route_host
                ):
                    if not _under(path, source_path):
                        continue
                    values = urllib.parse.parse_qs(
                        source_query, keep_blank_values=True
                    ).get("country")
                    if values:
                        explicit = True
                        countries.update(values)
                    else:
                        countries.add(None)
            # An absent source query identifies the default country. Its app
            # country also recognises an explicit request for that default.
            selected: Set[str] = set()
            if (
                explicit
                and all(source_countries.values())
                and (requested is None or len(set(requested)) == 1)
            ):
                wanted = requested[0] if requested else None
                for target, _ in candidates:
                    identity = self._identity(target)
                    countries = source_countries[identity]
                    if wanted in countries or (
                        wanted is not None
                        and None in countries
                        and wanted == self._country(target)
                    ):
                        selected.add(identity)
            if len(selected) != 1:
                raise ValueError(
                    f"{host}{path} has ambiguous deployment routing; "
                    "link its policyengine.org page"
                )
            candidates = [
                (t, h) for t, h in candidates if self._identity(t) in selected
            ]
        found: List[Target] = []
        for target, _ in candidates:
            if target not in found:
                found.append(target)
        return found


def linked(text: str, routes: Routes) -> Tuple[List[Target], List[str]]:
    """Everything an edition links that the check applies to, and every link
    it refuses."""
    targets: List[Target] = []
    refused: List[str] = []
    try:
        destinations = links(text)
    except ValueError as exc:
        return [], [str(exc)]
    for host, path, query in destinations:
        tracked = any(
            (host == h or host.endswith(f".{h}")) and path.startswith(prefix)
            for h, prefix in TRACKING
        )
        if tracked or any(
            host == h or host.endswith(f".{h}") for h in UNCHECKABLE_HOSTS
        ):
            problem = (
                f"{host}{path} hides where it leads (a tracking link or a shortener); "
                "link the policyengine.org page itself"
            )
            if problem not in refused:
                refused.append(problem)
            continue
        if host == SITE_HOST or host.endswith(f".{SITE_HOST}"):
            if host != SITE_HOST:
                continue
            found, problem = routes.on_site(path)
            if problem:
                refused.append(problem)
        else:
            try:
                found = routes.off_site(host, path, query)
            except ValueError as exc:
                refused.append(str(exc))
                continue
        targets.extend(t for t in found if t not in targets)
    return targets, refused


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


def _string_list(value: object, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(v, str) and v for v in value)
        and (bool(value) or not nonempty)
    )


def _valid_hostname(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    try:
        hostname = value.rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return len(hostname) <= 253 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label, re.I)
        for label in hostname.split(".")
    )


def _valid_page_url(value: object) -> bool:
    """A usable absolute HTTPS page URL, before any routing consumes it."""
    if (
        not isinstance(value, str)
        or not value
        or re.search(r"[\s\\\x00-\x1f\x7f]", value)
    ):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        # Reading the port also validates invalid and out-of-range ports.
        parsed.port
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and _valid_hostname(parsed.hostname)
        )
    except ValueError:
        return False


def check_registries(apps: object, posts: object) -> List[str]:
    """Validate every registry field this checker consumes before loading it."""
    errors = []
    for name, items in (("apps", apps), ("posts", posts)):
        where = f"policyengine-app-v2's {name} registry"
        if not isinstance(items, list):
            errors.append(f"{where} is not a JSON array")
            continue
        for position, item in enumerate(items):
            at = f"{where} item {position}"
            if not isinstance(item, dict):
                errors.append(f"{at} is not an object")
                continue
            if "tags" in item and not _string_list(item["tags"]):
                errors.append(f"{at} has malformed tags")
            block = item.get("comparables")
            if "comparables" in item and (
                not isinstance(block, dict)
                or any(
                    key in block
                    and (not isinstance(block[key], str) or not block[key].strip())
                    for key in ("status", "scorecardSource")
                )
            ):
                errors.append(f"{at} has malformed comparables metadata")
            if name == "apps":
                if (
                    not isinstance(item.get("slug"), str)
                    or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["slug"])
                    or not isinstance(item.get("countryId"), str)
                    or not re.fullmatch(r"[a-z]{2}", item["countryId"])
                ):
                    errors.append(f"{at} has no canonical slug or countryId")
                if "displayWithResearch" in item and not isinstance(
                    item["displayWithResearch"], bool
                ):
                    errors.append(f"{at} has a malformed displayWithResearch flag")
                if (
                    "source" in item
                    and item["source"] != ""
                    and not (
                        _valid_page_url(item["source"])
                        or (
                            isinstance(item["source"], str)
                            and item["source"].startswith("/")
                            and not item["source"].startswith("//")
                            and not re.search(r"[\s\\\x00-\x1f\x7f]", item["source"])
                        )
                    )
                ):
                    errors.append(f"{at} has a malformed source URL")
            elif (
                not isinstance(item.get("filename"), str)
                or not item["filename"].strip()
                or not post_slug(item["filename"])
            ):
                errors.append(f"{at} has no usable filename")
    return errors


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
            _string_list(rules.get(k), nonempty=True)
            for k in ("analysis_tags", "no_estimate_tags", "country_tags")
        )
        or rules.get("default_country") not in (rules.get("country_tags") or [])
    ):
        errors.append("the scorecard index publishes no complete entry_rules")
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
                elif not _string_list(s.get("results_pins")):
                    errors.append(f"{where} has a search with no results_pins")
        if not _string_list(entry.get("current_pins")):
            errors.append(f"{where} has no current_pins")
        if not _valid_page_url(entry.get("url")):
            errors.append(f"{where} has no valid absolute HTTPS page url")
        deployments = entry.get("deployments", [])
        if not _string_list(deployments) or not all(
            _valid_page_url(url) for url in deployments
        ):
            errors.append(f"{where} has a malformed deployments list of HTTPS URLs")
        comparisons = entry.get("comparisons", [])
        if not isinstance(comparisons, list):
            errors.append(f"{where} has no comparisons list")
            continue
        for c in comparisons:
            if (
                not isinstance(c, dict)
                or c.get("status") not in STATUSES
                or not isinstance(c.get("claim"), str)
                or (
                    "found_on" in c
                    and c["found_on"] is not None
                    and not is_date(c["found_on"])
                )
            ):
                errors.append(
                    f"{where} has a comparison with no claim, a status not in "
                    f"{STATUSES}, or a found_on that is not a date"
                )
                break
    return errors


def _canonical_route_path(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"/[a-z0-9/-]*", value) is not None
        and normalize_path(value) == value
    )


def _route_entry(value: object) -> Optional[Key]:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"app ([a-z]{2})/([a-z0-9]+(?:-[a-z0-9]+)*)", value)
    return ("app", match.group(1), match.group(2)) if match else None


def check_routes(routes: object, registry: Optional[Registry] = None) -> List[str]:
    """Every reason the downloaded route map cannot be trusted."""
    if not isinstance(routes, dict) or routes.get("schema") != ROUTES_SCHEMA:
        return [f"policyengine-app-v2's route map is not {ROUTES_SCHEMA}"]
    errors = []
    paths, hosts = routes.get("paths"), routes.get("hosts")
    if (
        not isinstance(paths, list)
        or not paths
        or not all(
            isinstance(p, dict)
            and _canonical_route_path(p.get("path"))
            and isinstance(p.get("prefix"), bool)
            and _route_entry(p.get("entry")) is not None
            for p in paths
        )
    ):
        errors.append("policyengine-app-v2's route map has malformed paths")
    if not isinstance(hosts, list) or not all(
        isinstance(h, dict)
        and isinstance(h.get("host"), str)
        and _valid_hostname(h["host"])
        and normalize_host(h["host"]) == h["host"]
        and _canonical_route_path(h.get("pathPrefix"))
        and _string_list(h.get("entries"), nonempty=True)
        and all(_route_entry(e) is not None for e in h["entries"])
        for h in hosts
    ):
        errors.append("policyengine-app-v2's route map has malformed hosts")
    if not errors and registry is not None:
        entries = [p["entry"] for p in paths]
        entries.extend(e for h in hosts for e in h["entries"])
        missing = sorted(
            {e for e in entries if _route_entry(e) not in registry.entries}
        )
        if missing:
            errors.append(
                "policyengine-app-v2's route map references missing registry entries: "
                + ", ".join(missing)
            )
    return errors


def record_for(entry: dict, index: dict) -> Tuple[str, Optional[dict]]:
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


def _page(target: Target, index: dict) -> str:
    kind, ref = target
    if kind == "record":
        return str(index["analyses"][ref].get("url") or ref)
    entry_kind, country, slug = ref  # type: ignore[misc]
    if entry_kind == "app":
        return f"policyengine.org/{country}/{slug}"
    return f"policyengine.org/research/{slug}"


def check_edition(
    name: str, text: str, on: str, routes: Routes, index: dict
) -> List[str]:
    """Every reason this edition may not go out on ``on``."""
    window = index["promotion_window_days"]
    registry = routes.registry
    targets, refused = linked(text, routes)
    errors = [f"{name}: {problem}" for problem in refused]
    checked: Set[str] = set()
    for target in targets:
        page = _page(target, index)
        if target[0] == "record":
            source, recorded = str(target[1]), index["analyses"][target[1]]
        else:
            entry = registry.entries[target[1]]  # type: ignore[index]
            if not registry.publishes_estimate(entry):
                continue
            source, recorded = record_for(entry, index)
            if recorded is None:
                errors.append(
                    f"{name}: {page} has no comparables record in the scorecard; "
                    f"run the comparables review ({source}) before sending"
                )
                continue
        if source in checked:
            continue
        checked.add(source)
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


def _get(url: str, accept: Optional[str] = None) -> requests.Response:
    headers = {"Accept": accept} if accept else {}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    last_error: Optional[Exception] = None
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            return response
        except Exception as error:  # noqa: BLE001 - every failure retries, then fails
            last_error = error
            time.sleep(2**attempt)
    raise SystemExit(f"could not read {url}: {last_error}")


def _pinned(url: str, commits: Dict[str, str]) -> str:
    """A raw main-branch URL at the commit main points to now, so a cached
    copy of the file is never read."""
    match = _RAW_MAIN.match(url)
    if not match:
        return url
    repo, path = match.groups()
    if repo not in commits:
        sha = _get(
            f"https://api.github.com/repos/{repo}/commits/main",
            accept="application/vnd.github.sha",
        ).text.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise SystemExit(f"could not resolve {repo}'s main branch: {sha[:80]!r}")
        commits[repo] = sha
    return f"https://raw.githubusercontent.com/{repo}/{commits[repo]}/{path}"


def _load(where: str, commits: Optional[Dict[str, str]] = None) -> object:
    if not where.startswith("https://"):
        return json.loads(Path(where).read_text(encoding="utf-8"))
    url = _pinned(where, commits if commits is not None else {})
    try:
        return _get(url).json()
    except ValueError as error:
        raise SystemExit(f"{url} is not JSON: {error}") from error


def run_check(
    files: Sequence[Path],
    apps: Optional[str] = None,
    posts: Optional[str] = None,
    index_source: Optional[str] = None,
    cutover: Optional[str] = None,
    today: Optional[str] = None,
    require_dates: bool = False,
    routes_source: Optional[str] = None,
) -> Tuple[List[Path], List[str]]:
    """Check every edition due on or after the cutover. The sources and the
    cutover default to the module's ``APPS_URL``, ``POSTS_URL``,
    ``ROUTES_URL``, ``INDEX_URL`` and ``PROMOTION_CUTOVER_DATE``, read when
    called. Returns the editions checked and every error; downloads nothing
    when none is due."""
    due, errors = due_editions(
        files, cutover or PROMOTION_CUTOVER_DATE, today, require_dates
    )
    if not due:
        return [], errors
    commits: Dict[str, str] = {}
    index = _load(index_source or INDEX_URL, commits)
    problems = check_index(index)
    route_map = _load(routes_source or ROUTES_URL, commits)
    problems += check_routes(route_map)
    if problems:
        return [path for path, _ in due], errors + problems
    app_items = _load(apps or APPS_URL, commits)
    post_items = _load(posts or POSTS_URL, commits)
    problems = check_registries(app_items, post_items)
    if problems:
        return [path for path, _ in due], errors + problems
    registry = Registry(app_items, post_items, index["entry_rules"])
    problems = check_routes(route_map, registry)
    if problems:
        return [path for path, _ in due], errors + problems
    routes = Routes(route_map, registry, index)
    for path, on in due:
        text = path.read_text(encoding="utf-8")
        errors.extend(check_edition(path.name, text, on, routes, index))
    return [path for path, _ in due], errors


HOW_TO_FIX = (
    "Run the comparables review for each analysis above (the "
    "policyengine-comparables-review skill, search kind prepromotion), merge its "
    "scorecard PR, then check again."
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m newsletter_uploader.comparables")
    parser.add_argument("paths", nargs="*", default=["editions"])
    parser.add_argument("--apps", default=None)
    parser.add_argument("--posts", default=None)
    parser.add_argument("--routes", default=None)
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
        routes_source=args.routes,
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
