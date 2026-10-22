"""Fresh comparables before a newsletter goes out (comparables.py).

Invariants:
- every way of writing a link to a research entry finds it (Hypothesis): with
  or without a scheme or www., in any case, escaped or encoded, with dot
  segments, a trailing dot on the host or trailing punctuation, through
  /research/ or /blog/ or a dated slug, through a path or redirect in
  policyengine-app-v2's route map, or to a deployment host in it;
- a post is found by its slug under any country;
- a scorecard record's own page and deployments lead to it, so an analysis
  taken off the registry is still held to its record;
- a shared host (GitHub Pages, one deployment serving two countries) leads
  only to the analyses under the linked path;
- every research entry is checked unless it is a post that is plainly not an
  analysis and declares no_estimate;
- a linked analysis passes exactly when the scorecard's fresh says so, on the
  cases the scorecard checks its own fresh against;
- an index or route map of the wrong shape fails with a message, never a
  traceback or a pass;
- sources are read at the commit their main branch points to;
- an undated file fails wherever dates are required; an upload is judged on
  the later of its date and today, before Mailchimp is touched;
- tracking links and shorteners are refused.
"""

import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from newsletter_uploader import comparables as cmp
from newsletter_uploader.cli import main as cli_main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WINDOW = 7
PUSH = "2026-11-02"
PIN = "PolicyEngine/test@" + "b" * 40 + ":" + "a" * 64
RULES = {
    "analysis_tags": ["policy", "autumn-budget", "tax", "technical"],
    "no_estimate_tags": ["org", "event", "giving"],
    "country_tags": ["uk", "us", "ca", "ng", "il"],
    "default_country": "us",
    "search_kinds": ["prepublish", "backfill", "reharvest", "prepromotion"],
}


def app(country, slug, source="", listed=True, tags=("policy",), **extra):
    return {
        "slug": slug,
        "countryId": country,
        "displayWithResearch": listed,
        "tags": [country, *tags],
        "source": source,
        **extra,
    }


APPS = [
    app(
        "uk",
        "childcare-100k-threshold",
        "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold",
    ),
    app(
        "uk",
        "scottish-budget-2026-27",
        "https://post-scottish-budget-dashboard.vercel.app/",
    ),
    app(
        "us",
        "obbba-households",
        "https://obbba-household-by-household.vercel.app/us/obbba-households",
    ),
    app("us", "aca-calc", listed=False),
    app("us", "cliffwatch", "https://cliff-watch.vercel.app/"),
    app(
        "us",
        "bill-tracker",
        "https://policyengine--state-legislative-tracker.modal.run/",
    ),
    app("us", "california-wealth-tax", "/us/california-wealth-tax/embed"),
    app("us", "tanf-calculator", "https://policyengine.github.io/tanf-calculator"),
    app(
        "uk",
        "uk-salary-sacrifice-tool",
        "https://policyengine.github.io/uk-salary-sacrifice-analysis",
    ),
    app(
        "uk",
        "marriage",
        "https://marriage-zeta-beryl.vercel.app/us/marriage?country=uk",
        comparables={"status": "no_estimate", "reason": "a household calculator"},
    ),
    app("us", "marriage", "https://marriage-zeta-beryl.vercel.app/us/marriage"),
    app("us", "year-in-review", listed=False, tags=("featured",)),
]
POSTS = [
    {"filename": "UK_Two_Child_Limit.md", "tags": ["uk", "policy"]},
    {"filename": "fuel-duty-freeze.md", "tags": ["uk", "autumn-budget", "featured"]},
    {"filename": "childcare-expansion-2023.md", "tags": ["uk", "policy"]},
    {
        "filename": "giving-tuesday.md",
        "tags": ["us", "giving"],
        "comparables": {
            "status": "no_estimate",
            "reason": "an appeal, not an analysis",
        },
    },
    {
        "filename": "giving-and-policy.md",
        "tags": ["us", "giving", "policy"],
        "comparables": {"status": "no_estimate", "reason": "policy wins over this"},
    },
    {"filename": "api-v2.md", "tags": ["global", "technical"]},
    {
        "filename": "joint-post.md",
        "tags": ["uk", "us", "policy"],
        "comparables": {
            "status": "reviewed",
            "scorecardSource": "analysis-uk-joint-post",
        },
    },
]


def route(path, entry, prefix=True):
    return {"path": path, "prefix": prefix, "entry": entry}


def host(name, entries, prefix="/"):
    return {"host": name, "pathPrefix": prefix, "entries": entries}


# policyengine-app-v2's route map for these apps, as its build would write it
ROUTE_MAP = {
    "schema": cmp.ROUTES_SCHEMA,
    "paths": [
        *(
            route(f"/{a['countryId']}/{a['slug']}", f"app {a['countryId']}/{a['slug']}")
            for a in APPS
            if a["displayWithResearch"] or "policy" in a["tags"]
        ),
        route("/us/ob3-households", "app us/obbba-households"),
        route("/us/obbba-household-explorer", "app us/obbba-households"),
        route(
            "/us/research/obbba-household-explorer", "app us/obbba-households", False
        ),
        route("/us/aca-reforms-calculator", "app us/aca-calc"),
        route("/us/cliff-watch", "app us/cliffwatch"),
        route("/uk/cliff-watch", "app us/cliffwatch"),
        route("/uk/cliffwatch", "app us/cliffwatch"),
        route("/us/state-legislative-tracker", "app us/bill-tracker"),
        route("/uk/state-legislative-tracker", "app us/bill-tracker"),
        route("/uk/bill-tracker", "app us/bill-tracker"),
    ],
    "hosts": [
        host(
            "uk-childcare-100k-threshold.vercel.app",
            ["app uk/childcare-100k-threshold"],
        ),
        host(
            "post-scottish-budget-dashboard.vercel.app",
            ["app uk/scottish-budget-2026-27"],
        ),
        host("obbba-household-by-household.vercel.app", ["app us/obbba-households"]),
        host("cliff-watch.vercel.app", ["app us/cliffwatch"]),
        host(
            "policyengine--state-legislative-tracker.modal.run", ["app us/bill-tracker"]
        ),
        host("california-wealth-tax.vercel.app", ["app us/california-wealth-tax"]),
        host("policyengine.github.io", ["app us/tanf-calculator"], "/tanf-calculator"),
        host(
            "policyengine.github.io",
            ["app uk/uk-salary-sacrifice-tool"],
            "/uk-salary-sacrifice-analysis",
        ),
        host(
            "marriage-zeta-beryl.vercel.app",
            ["app uk/marriage", "app us/marriage"],
            "/us/marriage",
        ),
    ],
}


def shift(date, days):
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def record(
    kind,
    slug,
    search_dates,
    pending_found=(),
    pins_match=True,
    country="uk",
    deployments=(),
):
    return {
        "kind": kind,
        "slug": slug,
        "url": f"https://policyengine.org/{country}/{slug}",
        "deployments": list(deployments),
        "current_pins": [PIN],
        "searches": [
            {
                "date": d,
                "kind": "reharvest",
                "results_pins": [PIN] if pins_match else [],
            }
            for d in search_dates
        ],
        "comparisons": [
            {"claim": f"c{i}", "status": "pending", "found_on": found}
            for i, found in enumerate(pending_found)
        ],
    }


def index(analyses):
    return {
        "schema": cmp.INDEX_SCHEMA,
        "promotion_window_days": WINDOW,
        "entry_rules": copy.deepcopy(RULES),
        "analyses": copy.deepcopy(analyses),
    }


CHILDCARE = ("app", "uk", "childcare-100k-threshold")
FRESH_CHILDCARE = {
    "analysis-uk-childcare-100k-threshold": record(
        "app", "childcare-100k-threshold", [PUSH]
    )
}
STALE_CHILDCARE = {
    "analysis-uk-childcare-100k-threshold": record(
        "app", "childcare-100k-threshold", ["2026-01-01"]
    )
}


def routes_for(apps=APPS, posts=POSTS, analyses=None):
    registry = cmp.Registry(apps, posts, RULES)
    return cmp.Routes(ROUTE_MAP, registry, index(analyses or {}))


def targets(text, **kwargs):
    found, _ = cmp.linked(text, routes_for(**kwargs))
    return found


def entry(key):
    return ("entry", key)


# --- recognising a link ---

SCHEMES = ["https://", "http://", "//", "", "HTTPS://"]
HOSTS = [
    "policyengine.org",
    "www.policyengine.org",
    "PolicyEngine.org",
    "policyengine.org:443",
    "policyengine.org.",
]
TRAILS = [
    "",
    "/",
    "?utm_source=x",
    "#top",
    ".",
    ",",
    ")",
    "**",
    "_",
    "\u2014",
    "\u2019",
    "&nbsp;",
    "&utm=1",
    "|",
    "*",
    "/deep/path",
]


def written(path, scheme, host_, trail, encode):
    url = f"{scheme}{host_}{path}{trail}"
    if encode == "html":
        url = url.replace("/", "&#47;").replace("-", "&#45;")
    elif encode == "percent":
        url = url.replace("-", "%2D")
    return f"<p>Read <a href='{url}'>this</a> now</p>"


@settings(max_examples=400, deadline=None)
@given(
    target=st.sampled_from(
        [
            ("/uk/childcare-100k-threshold", CHILDCARE),
            ("/UK/Childcare-100k-Threshold", CHILDCARE),
            ("//uk/childcare-100k-threshold", CHILDCARE),
            ("/uk/./childcare-100k-threshold", CHILDCARE),
            ("/uk/research/../childcare-100k-threshold", CHILDCARE),
            ("/uk/research/uk-two-child-limit", ("post", "", "uk-two-child-limit")),
            ("/uk/research/UK_Two_Child_Limit", ("post", "", "uk-two-child-limit")),
            ("/uk/blog/uk-two-child-limit", ("post", "", "uk-two-child-limit")),
            (
                "/uk/research/2025-01-01-uk-two-child-limit",
                ("post", "", "uk-two-child-limit"),
            ),
            (
                "/us/research/childcare-expansion-2023",
                ("post", "", "childcare-expansion-2023"),
            ),
            ("/us/ob3-households", ("app", "us", "obbba-households")),
            ("/us/obbba-household-explorer/x", ("app", "us", "obbba-households")),
            (
                "/us/research/obbba-household-explorer",
                ("app", "us", "obbba-households"),
            ),
            ("/us/aca-reforms-calculator", ("app", "us", "aca-calc")),
            ("/us/cliff-watch", ("app", "us", "cliffwatch")),
            (
                "/us/state-legislative-tracker/MN/mn-hf4621",
                ("app", "us", "bill-tracker"),
            ),
            ("/uk/bill-tracker", ("app", "us", "bill-tracker")),
            ("/uk/cliffwatch", ("app", "us", "cliffwatch")),
        ]
    ),
    scheme=st.sampled_from(SCHEMES),
    host_=st.sampled_from(HOSTS),
    trail=st.sampled_from(TRAILS),
    encode=st.sampled_from(["none", "html", "percent"]),
)
def test_every_way_of_writing_a_link_finds_its_entry(
    target, scheme, host_, trail, encode
):
    path, key = target
    # the site redirects that old research path exactly, not paths under it
    assume(not (path.startswith("/us/research/obbba") and trail == "/deep/path"))
    assert entry(key) in targets(written(path, scheme, host_, trail, encode))


def test_the_scottish_budget_social_post_link_is_found():
    text = "Explore it at policyengine.org/uk/scottish-budget-2026-27 today."
    assert targets(text) == [entry(("app", "uk", "scottish-budget-2026-27"))]


@pytest.mark.parametrize(
    "link, key",
    [
        (
            "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold",
            CHILDCARE,
        ),
        ("uk-childcare-100k-threshold.vercel.app", CHILDCARE),
        (
            "https://uk-childcare-100k-threshold-git-dev-policy-engine.vercel.app/",
            CHILDCARE,
        ),
        (
            "https://policyengine--state-legislative-tracker.modal.run/",
            ("app", "us", "bill-tracker"),
        ),
        (
            "https://california-wealth-tax.vercel.app/",
            ("app", "us", "california-wealth-tax"),
        ),
        (
            "https://policyengine.github.io/tanf-calculator/",
            ("app", "us", "tanf-calculator"),
        ),
    ],
)
def test_a_deployment_link_finds_its_app(link, key):
    assert targets(link) == [entry(key)]


def test_a_shared_host_leads_only_to_the_analyses_under_the_path():
    assert targets("https://policyengine.github.io/uk-salary-sacrifice-analysis/") == [
        entry(("app", "uk", "uk-salary-sacrifice-tool"))
    ]
    assert targets("https://policyengine.github.io/plugin-blog/") == []
    assert targets("https://marriage-zeta-beryl.vercel.app/us/marriage") == [
        entry(("app", "uk", "marriage")),
        entry(("app", "us", "marriage")),
    ]
    assert targets("https://unrelated.vercel.app/") == []


def test_an_analysis_off_the_registry_is_held_to_its_record_on_every_link():
    apps = [a for a in APPS if a["slug"] != "childcare-100k-threshold"]
    deployed = {
        "analysis-uk-childcare-100k-threshold": record(
            "app",
            "childcare-100k-threshold",
            ["2026-01-01"],
            deployments=[
                "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold"
            ],
        )
    }
    routes = cmp.Routes(
        {
            **ROUTE_MAP,
            "hosts": [h for h in ROUTE_MAP["hosts"] if "childcare" not in h["host"]],
            "paths": [p for p in ROUTE_MAP["paths"] if "childcare" not in p["path"]],
        },
        cmp.Registry(apps, POSTS, RULES),
        index(deployed),
    )
    for link in (
        "policyengine.org/uk/childcare-100k-threshold",
        "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold",
        "https://uk-childcare-100k-threshold.vercel.app/",
    ):
        errors = cmp.check_edition("e.html", link, PUSH, routes, index(deployed))
        assert errors and "no comparables search between" in errors[0], link


def test_other_pages_are_not_analyses():
    text = (
        "policyengine.org policyengine.org/uk policyengine.org/uk/research "
        "policyengine.org/us/donate hello@policyengine.org "
        "legacy.policyengine.org/uk/x "
        "policyengine.org/us/year-in-review"
    )
    assert targets(text) == []


def test_tracking_links_and_shorteners_are_refused():
    routes = routes_for()
    _, refused = cmp.linked(
        "https://policyengine.us5.list-manage.com/track/click?u=1 bit.ly/abc "
        "https://t.co/x https://policyengine.us5.list-manage.com./track/click?u=2",
        routes,
    )
    assert len(refused) == 3  # the trailing-dot host is the same link
    _, refused = cmp.linked(
        "https://policyengine.us5.list-manage.com/unsubscribe?u=1 "
        "https://policyengine.us5.list-manage.com/profile?u=1",
        routes,
    )
    assert refused == []


def test_a_research_link_to_no_post_is_refused():
    _, refused = cmp.linked("policyengine.org/uk/research/no-such-post", routes_for())
    assert refused == ["policyengine.org/uk/research/no-such-post is not a post"]


def test_paths_normalise_like_the_site():
    assert cmp.normalize_path("/uk/research/../x.") == "/uk/x"
    assert cmp.normalize_path("//UK/./Two_Child") == "/uk/two-child"
    assert cmp.normalize_host("WWW.PolicyEngine.org.") == "policyengine.org"


def test_post_slug_is_the_websites():
    assert cmp.post_slug("UK_Two_Child_Limit.md") == "uk-two-child-limit"
    assert cmp.post_slug("a.b.md") == "a"


# --- which entries are checked ---


def test_every_entry_is_checked_unless_it_may_declare_no_estimate():
    reg = cmp.Registry(APPS, POSTS, RULES)
    checked = {k for k, e in reg.entries.items() if reg.publishes_estimate(e)}
    assert ("post", "", "fuel-duty-freeze") in checked  # an untagged costing
    assert ("post", "", "giving-and-policy") in checked  # policy wins
    assert ("app", "uk", "marriage") in checked  # an app never declares it
    assert ("post", "", "api-v2") in checked
    assert ("post", "", "giving-tuesday") not in checked
    # an app neither listed with research nor tagged policy is not an entry
    assert ("app", "us", "year-in-review") not in reg.entries


def test_a_post_with_no_country_tag_is_filed_under_the_default():
    reg = cmp.Registry(APPS, POSTS, RULES)
    assert reg.entries[("post", "", "api-v2")]["countries"] == ["us"]


def test_a_post_is_checked_against_the_record_its_block_names():
    analyses = {"analysis-uk-joint-post": record("post", "joint-post", [PUSH])}
    routes = routes_for(analyses=analyses)
    errors = cmp.check_edition(
        "e.html",
        "policyengine.org/us/research/joint-post",
        PUSH,
        routes,
        index(analyses),
    )
    assert errors == []


def test_a_post_linked_under_another_country_is_still_checked():
    errors = cmp.check_edition(
        "e.html",
        "https://policyengine.org/us/research/childcare-expansion-2023",
        PUSH,
        routes_for(),
        index({}),
    )
    assert errors and "analysis-uk-childcare-expansion-2023" in errors[0]


def test_a_record_of_another_kind_or_slug_does_not_count():
    analyses = {
        "analysis-uk-childcare-100k-threshold": record(
            "post", "childcare-100k-threshold", [PUSH]
        )
    }
    errors = cmp.check_edition(
        "e.html",
        "https://uk-childcare-100k-threshold.vercel.app/",
        PUSH,
        routes_for(analyses={}),
        index(analyses),
    )
    assert errors and "no comparables record" in errors[0]


# --- freshness: the scorecard's rule ---


def test_fresh_agrees_with_the_scorecards_cases():
    cases = json.loads((FIXTURES / "comparables_fresh_cases.json").read_text())
    assert len(cases) > 50
    for case in cases:
        assert (cmp.fresh(case["entry"], case["on"], case["window"]) == []) == case[
            "fresh"
        ], case


def test_a_pending_gap_with_no_found_on_counts_as_found():
    rec = record("app", "x", [PUSH])
    rec["comparisons"] = [{"claim": "c", "status": "pending"}]
    assert cmp.fresh(rec, PUSH, WINDOW)


@settings(max_examples=200, deadline=None)
@given(
    offsets=st.lists(st.integers(-60, 60), min_size=1, max_size=5),
    window=st.integers(1, 30),
    pending=st.one_of(st.none(), st.integers(-30, 30)),
)
def test_an_edition_passes_exactly_when_its_analysis_is_fresh(offsets, window, pending):
    dates = sorted(shift(PUSH, o) for o in offsets)
    rec = record(
        "app",
        "childcare-100k-threshold",
        dates,
        pending_found=() if pending is None else [shift(PUSH, pending)],
    )
    analyses = {"analysis-uk-childcare-100k-threshold": rec}
    idx = dict(index(analyses), promotion_window_days=window)
    errors = cmp.check_edition(
        "e.html",
        "policyengine.org/uk/childcare-100k-threshold",
        PUSH,
        routes_for(analyses=analyses),
        idx,
    )
    in_window = any(-window <= o <= 0 for o in offsets)
    blocked = pending is not None and pending <= 0
    assert (errors == []) == (in_window and not blocked)


def test_a_search_against_old_results_is_not_fresh():
    rec = record("app", "childcare-100k-threshold", [PUSH], pins_match=False)
    analyses = {"analysis-uk-childcare-100k-threshold": rec}
    errors = cmp.check_edition(
        "e.html",
        "policyengine.org/uk/childcare-100k-threshold",
        PUSH,
        routes_for(analyses=analyses),
        index(analyses),
    )
    assert errors and "compared the results the page reads now" in errors[0]


# --- the index's and route map's shape ---


def good_index():
    return index(FRESH_CHILDCARE)


A = "analysis-uk-childcare-100k-threshold"


@pytest.mark.parametrize(
    "breaks",
    [
        lambda i: i.update(schema="comparables/index/0"),
        lambda i: i.pop("promotion_window_days"),
        lambda i: i.update(promotion_window_days="7"),
        lambda i: i.update(promotion_window_days=True),
        lambda i: i.update(promotion_window_days=7.9),
        lambda i: i.update(promotion_window_days=3650),
        lambda i: i.update(promotion_window_days=0),
        lambda i: i.pop("analyses"),
        lambda i: i.update(analyses=[]),
        lambda i: i.pop("entry_rules"),
        lambda i: i["entry_rules"].update(country_tags=[]),
        lambda i: i["entry_rules"].update(default_country="xx"),
        lambda i: i["analyses"][A].update(searches=None),
        lambda i: i["analyses"][A].update(searches=[]),
        lambda i: i["analyses"][A]["searches"][0].update(date="soon"),
        lambda i: i["analyses"][A]["searches"][0].pop("results_pins"),
        lambda i: i["analyses"][A].pop("current_pins"),
        lambda i: i["analyses"][A].update(current_pins=[{}, "x"]),
        lambda i: i["analyses"][A].pop("url"),
        lambda i: i["analyses"][A].update(deployments="x"),
        lambda i: i["analyses"][A].update(comparisons=[{"claim": "c"}]),
        lambda i: i["analyses"][A].update(
            comparisons=[{"status": "pending", "found_on": "2026-11-02"}]
        ),
        lambda i: i["analyses"][A].update(
            comparisons=[{"claim": "c", "status": "PENDING"}]
        ),
        lambda i: i["analyses"][A].update(
            comparisons=[{"claim": "c", "status": "pending", "found_on": "9999"}]
        ),
    ],
)
def test_an_index_of_the_wrong_shape_fails_with_a_message(breaks, tmp_path):
    idx = good_index()
    breaks(idx)
    assert cmp.check_index(idx)
    sources = write_sources(tmp_path, FRESH_CHILDCARE)
    Path(sources["index_source"]).write_text(json.dumps(idx))
    edition = make_edition(tmp_path, f"{PUSH}-uk.html")
    due, errors = cmp.run_check([edition], **sources, cutover="2026-10-26")
    assert due == [edition] and errors


def test_a_good_index_passes():
    assert cmp.check_index(good_index()) == []


@pytest.mark.parametrize(
    "routes",
    [
        {"schema": "x", "paths": [], "hosts": []},
        {**ROUTE_MAP, "paths": []},
        {**ROUTE_MAP, "paths": [{"path": "uk/x", "prefix": True, "entry": "app uk/x"}]},
        {
            **ROUTE_MAP,
            "hosts": [{"host": "a.vercel.app", "pathPrefix": "/", "entries": []}],
        },
        [],
    ],
)
def test_a_route_map_of_the_wrong_shape_fails(routes):
    assert cmp.check_routes(routes)


def test_sources_are_read_at_the_commit_main_points_to(monkeypatch):
    calls = []

    class Response:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def get(url, timeout, headers):
        calls.append((url, headers))
        return Response("c" * 40 if "api.github.com" in url else "{}")

    monkeypatch.setattr(cmp.requests, "get", get)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    commits = {}
    url = (
        "https://raw.githubusercontent.com/PolicyEngine/policyengine-app-v2/main/a.json"
    )
    cmp._load(url, commits)
    cmp._load(url.replace("a.json", "b.json"), commits)
    api = [c for c in calls if "api.github.com" in c[0]]
    assert len(api) == 1 and api[0][1]["Authorization"] == "Bearer t"
    assert calls[-1][0].endswith(f"/{'c' * 40}/b.json")

    monkeypatch.setattr(cmp.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        cmp.requests, "get", lambda url, timeout, headers: Response("not a sha")
    )
    with pytest.raises(SystemExit, match="could not resolve"):
        cmp._load(url, {})


# --- editions and their dates ---


@pytest.mark.parametrize(
    "name, date",
    [
        ("2026-11-02-uk.html", "2026-11-02"),
        ("2026-11-02.html", "2026-11-02"),
        ("2026-11-02_uk.html", "2026-11-02"),
        ("2026-11-02-uk-social.md", "2026-11-02"),
        ("uk-2026-11-02.html", None),
        ("draft.html", None),
        ("2026-11-31-uk.html", None),
        ("2026-11-0212.html", None),
    ],
)
def test_edition_dates(name, date):
    assert cmp.edition_date(Path(name)) == date


def write_sources(tmp_path, analyses, apps=APPS, posts=POSTS):
    for name, data in (
        ("apps.json", apps),
        ("posts.json", posts),
        ("index.json", index(analyses)),
        ("routes.json", ROUTE_MAP),
    ):
        (tmp_path / name).write_text(json.dumps(data))
    return dict(
        apps=str(tmp_path / "apps.json"),
        posts=str(tmp_path / "posts.json"),
        index_source=str(tmp_path / "index.json"),
        routes_source=str(tmp_path / "routes.json"),
    )


def make_edition(tmp_path, name, body="policyengine.org/uk/childcare-100k-threshold"):
    path = tmp_path / name
    path.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")
    return path


def test_an_undated_file_fails_where_dates_are_required(tmp_path):
    sources = write_sources(tmp_path, FRESH_CHILDCARE)
    for name in ("draft.html", "uk-2026-11-02.html", "2026-11-31-uk.html"):
        path = make_edition(tmp_path, name)
        due, errors = cmp.run_check([path], **sources, require_dates=True)
        assert due == [] and errors and "no YYYY-MM-DD date" in errors[0]
        assert cmp.run_check([path], **sources) == ([], [])


def test_nothing_before_the_cutover_is_checked_or_downloaded(tmp_path):
    path = make_edition(tmp_path, "2026-10-25-uk.html")
    missing = str(tmp_path / "missing.json")
    assert cmp.run_check([path], missing, missing, missing, cutover="2026-10-26") == (
        [],
        [],
    )


def test_an_upload_after_the_editions_date_is_judged_today(tmp_path):
    sources = write_sources(
        tmp_path,
        {
            "analysis-uk-childcare-100k-threshold": record(
                "app", "childcare-100k-threshold", ["2026-11-20"]
            )
        },
    )
    path = make_edition(tmp_path, "2026-10-25-uk.html")
    # judged on its own date before the cutover: not due
    assert cmp.run_check([path], **sources, cutover="2026-10-26")[0] == []
    # uploaded on 2026-11-21: due, and a search on the 20th counts
    assert cmp.run_check(
        [path], **sources, cutover="2026-10-26", today="2026-11-21"
    ) == ([path], [])
    # uploaded on 2026-12-21: the search is stale
    due, errors = cmp.run_check(
        [path], **sources, cutover="2026-10-26", today="2026-12-21"
    )
    assert due == [path] and errors


def test_a_directory_is_scanned_for_every_edition_like_file(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in (
        "2026-11-02-uk.HTML",
        "sub/2026-11-03-uk.htm",
        "2026-11-04-social.md",
        "notes.txt",
    ):
        (tmp_path / name).write_text("x", encoding="utf-8")
    names = sorted(p.name for p in cmp.edition_files([tmp_path]))
    assert names == ["2026-11-02-uk.HTML", "2026-11-03-uk.htm", "2026-11-04-social.md"]


def test_main_passes_and_fails(tmp_path, capsys):
    sources = write_sources(tmp_path, FRESH_CHILDCARE)
    path = make_edition(tmp_path, f"{PUSH}-uk.html")
    args = [
        str(path),
        "--apps",
        sources["apps"],
        "--posts",
        sources["posts"],
        "--index",
        sources["index_source"],
        "--routes",
        sources["routes_source"],
    ]
    assert cmp.main(args) == 0
    assert f"ok   {path.name}" in capsys.readouterr().out
    write_sources(tmp_path, STALE_CHILDCARE)
    assert cmp.main(args) == 1
    out = capsys.readouterr().out
    assert f"FAIL {path.name}" in out and "run a prepromotion search" in out


def test_main_prints_no_verdicts_when_the_index_is_bad(tmp_path, capsys):
    sources = write_sources(tmp_path, FRESH_CHILDCARE)
    bad = dict(index(FRESH_CHILDCARE), schema="nope")
    Path(sources["index_source"]).write_text(json.dumps(bad))
    path = make_edition(tmp_path, f"{PUSH}-uk.html")
    args = [
        str(path),
        "--apps",
        sources["apps"],
        "--posts",
        sources["posts"],
        "--index",
        sources["index_source"],
        "--routes",
        sources["routes_source"],
    ]
    assert cmp.main(args) == 1
    out = capsys.readouterr().out
    assert "ok   " not in out and "schema" in out


def test_an_unreadable_source_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(cmp.time, "sleep", lambda _s: None)

    def refuse(*_a, **_k):
        raise OSError("network down")

    monkeypatch.setattr(cmp.requests, "get", refuse)
    path = make_edition(tmp_path, f"{PUSH}-uk.html")
    with pytest.raises(SystemExit, match="could not read"):
        cmp.run_check(
            [path],
            index_source="https://example.invalid/index.json",
            cutover="2026-10-26",
        )


# --- the upload command ---


def upload(path, mocker, extra=()):
    client = mocker.patch("newsletter_uploader.cli.MailchimpClient")
    result = CliRunner().invoke(
        cli_main,
        [
            str(path),
            "--audience",
            "uk",
            "--subject",
            "s",
            "--preview",
            "p",
            "--api-key",
            "k-us5",
            *extra,
        ],
    )
    return result, client


@pytest.mark.parametrize("campaign", [(), ("--campaign-id", "abc")])
def test_upload_refuses_a_stale_edition_before_mailchimp(
    tmp_path, mocker, monkeypatch, campaign
):
    sources = write_sources(tmp_path, STALE_CHILDCARE)
    monkeypatch.setattr(cmp, "APPS_URL", sources["apps"])
    monkeypatch.setattr(cmp, "POSTS_URL", sources["posts"])
    monkeypatch.setattr(cmp, "INDEX_URL", sources["index_source"])
    monkeypatch.setattr(cmp, "ROUTES_URL", sources["routes_source"])
    path = make_edition(tmp_path, "2026-11-02-uk.html")
    result, client = upload(path, mocker, campaign)
    assert result.exit_code == 1
    assert "not fresh" in result.output
    client.assert_not_called()


@pytest.mark.parametrize(
    "name", ["draft.html", "2026-11-02_uk.html", "uk-2026-11-02.html"]
)
def test_upload_refuses_an_undated_file_before_mailchimp(tmp_path, mocker, name):
    path = make_edition(tmp_path, name)
    result, client = upload(path, mocker)
    if cmp.edition_date(path) is None:
        assert result.exit_code == 1
        assert "no YYYY-MM-DD date" in result.output
        client.assert_not_called()


def test_upload_judges_an_old_edition_on_today(tmp_path, mocker, monkeypatch):
    sources = write_sources(tmp_path, STALE_CHILDCARE)
    monkeypatch.setattr(cmp, "APPS_URL", sources["apps"])
    monkeypatch.setattr(cmp, "POSTS_URL", sources["posts"])
    monkeypatch.setattr(cmp, "INDEX_URL", sources["index_source"])
    monkeypatch.setattr(cmp, "ROUTES_URL", sources["routes_source"])
    monkeypatch.setattr(cmp, "today_utc", lambda: "2026-11-30")
    path = make_edition(tmp_path, "2026-10-01-uk.html")
    result, client = upload(path, mocker)
    assert result.exit_code == 1
    client.assert_not_called()
