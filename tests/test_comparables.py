"""Fresh comparables before a newsletter goes out (comparables.py).

Invariants:
- every way of writing a link to a research entry finds it (Hypothesis): with
  or without a scheme or www., in any case, escaped or encoded, with any
  trailing punctuation, through /research/ or /blog/ or a dated slug, through
  a redirect in ALIASES, or to the app's own host;
- a post is found by its slug under any country;
- every research entry is checked unless it is a post that is plainly not an
  analysis and declares no_estimate;
- a linked analysis passes exactly when the scorecard's fresh says so, on the
  cases the scorecard checks its own fresh against;
- an index of the wrong shape fails with a message, never a traceback;
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
from hypothesis import given, settings
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

APPS = [
    {
        "slug": "childcare-100k-threshold",
        "countryId": "uk",
        "displayWithResearch": True,
        "tags": ["uk", "featured", "policy", "interactives"],
        "source": "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold",
    },
    {
        "slug": "scottish-budget-2026-27",
        "countryId": "uk",
        "displayWithResearch": True,
        "tags": ["uk", "policy"],
        "source": "https://post-scottish-budget-dashboard.vercel.app/",
    },
    {
        "slug": "obbba-households",
        "countryId": "us",
        "displayWithResearch": True,
        "tags": ["us", "policy"],
        "source": "https://obbba-household-by-household.vercel.app/us/obbba-households",
    },
    {"slug": "aca-calc", "countryId": "us", "tags": ["us", "policy"]},
    {
        "slug": "cliffwatch",
        "countryId": "us",
        "displayWithResearch": True,
        "tags": ["us"],
    },
    {
        "slug": "marriage",
        "countryId": "uk",
        "displayWithResearch": True,
        "tags": ["uk", "policy"],
        "comparables": {"status": "no_estimate", "reason": "a household calculator"},
    },
    {"slug": "year-in-review", "countryId": "us", "tags": ["us", "featured"]},
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


def shift(date, days):
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def registry():
    return cmp.Registry(APPS, POSTS, RULES)


def record(kind, slug, search_dates, pending_found=(), pins_match=True):
    return {
        "kind": kind,
        "slug": slug,
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
        "entry_rules": RULES,
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


def keys(text):
    found, _ = cmp.linked_analyses(text, registry())
    return found


# --- recognising a link ---

SCHEMES = ["https://", "http://", "//", "", "HTTPS://"]
HOSTS = [
    "policyengine.org",
    "www.policyengine.org",
    "PolicyEngine.org",
    "policyengine.org:443",
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
    "—",
    "’",
    "&nbsp;",
    "&utm=1",
    "|",
    "*",
    "/deep/path",
]


def written(path, scheme, host, trail, encode):
    url = f"{scheme}{host}{path}{trail}"
    if encode == "html":
        url = url.replace("/", "&#47;").replace("-", "&#45;")
    elif encode == "percent":
        url = url.replace("-", "%2D")
    return f"<p>Read <a href='{url}'>this</a> now</p>"


@settings(max_examples=300, deadline=None)
@given(
    target=st.sampled_from(
        [
            ("/uk/childcare-100k-threshold", CHILDCARE),
            ("/UK/Childcare-100k-Threshold", CHILDCARE),
            ("//uk/childcare-100k-threshold", CHILDCARE),
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
        ]
    ),
    scheme=st.sampled_from(SCHEMES),
    host=st.sampled_from(HOSTS),
    trail=st.sampled_from(TRAILS),
    encode=st.sampled_from(["none", "html", "percent"]),
)
def test_every_way_of_writing_a_link_finds_its_entry(
    target, scheme, host, trail, encode
):
    path, key = target
    assert key in keys(written(path, scheme, host, trail, encode))


def test_the_scottish_budget_social_post_link_is_found():
    text = "Explore it at policyengine.org/uk/scottish-budget-2026-27 today."
    assert keys(text) == [("app", "uk", "scottish-budget-2026-27")]


def test_an_apps_own_host_and_its_previews_are_found():
    assert keys(
        "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold"
    ) == [CHILDCARE]
    assert keys("uk-childcare-100k-threshold.vercel.app") == [CHILDCARE]
    assert keys(
        "https://uk-childcare-100k-threshold-git-dev-policy-engine.vercel.app/"
    ) == [CHILDCARE]
    assert keys("https://unrelated.vercel.app/") == []


def test_other_pages_are_not_analyses():
    text = (
        "policyengine.org policyengine.org/uk policyengine.org/uk/research "
        "policyengine.org/us/donate hello@policyengine.org "
        "legacy.policyengine.org/uk/x "
        "policyengine.org/us/year-in-review"
    )
    assert keys(text) == []


def test_tracking_links_and_shorteners_are_refused():
    _, refused = cmp.linked_analyses(
        "https://policyengine.us5.list-manage.com/track/click?u=1 bit.ly/abc https://t.co/x",
        registry(),
    )
    assert len(refused) == 3
    _, refused = cmp.linked_analyses(
        "https://policyengine.us5.list-manage.com/unsubscribe?u=1 "
        "https://policyengine.us5.list-manage.com/profile?u=1",
        registry(),
    )
    assert refused == []


def test_a_research_link_to_no_post_is_refused():
    _, refused = cmp.linked_analyses(
        "policyengine.org/uk/research/no-such-post", registry()
    )
    assert refused == ["policyengine.org/uk/research/no-such-post is not a post"]


def test_post_slug_is_the_websites():
    assert cmp.post_slug("UK_Two_Child_Limit.md") == "uk-two-child-limit"
    assert cmp.post_slug("a.b.md") == "a"


# --- which entries are checked ---


def test_every_entry_is_checked_unless_it_may_declare_no_estimate():
    reg = registry()
    checked = {k for k, e in reg.entries.items() if reg.publishes_estimate(e)}
    assert ("post", "", "fuel-duty-freeze") in checked  # an untagged costing
    assert ("post", "", "giving-and-policy") in checked  # policy wins
    assert ("app", "uk", "marriage") in checked  # an app never declares it
    assert ("post", "", "api-v2") in checked
    assert ("post", "", "giving-tuesday") not in checked
    # an app neither listed with research nor tagged policy is not an entry
    assert ("app", "us", "year-in-review") not in reg.entries


def test_a_post_with_no_country_tag_is_filed_under_the_default():
    assert registry().entries[("post", "", "api-v2")]["countries"] == ["us"]


def test_a_post_is_checked_against_the_record_its_block_names():
    reg = registry()
    key = ("post", "", "joint-post")
    entry = reg.entries[key]
    analyses = {"analysis-uk-joint-post": record("post", "joint-post", [PUSH])}
    assert cmp.record_for(key, entry, index(analyses))[0] == "analysis-uk-joint-post"
    errors = cmp.check_edition(
        "e.html", "policyengine.org/us/research/joint-post", PUSH, reg, index(analyses)
    )
    assert errors == []


def test_a_post_linked_under_another_country_is_still_checked():
    errors = cmp.check_edition(
        "e.html",
        "https://policyengine.org/us/research/childcare-expansion-2023",
        PUSH,
        registry(),
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
        "policyengine.org/uk/childcare-100k-threshold",
        PUSH,
        registry(),
        index(analyses),
    )
    assert errors and "no comparables record" in errors[0]


def test_a_page_off_the_registry_is_held_to_its_scorecard_record():
    reg = cmp.Registry(
        [a for a in APPS if a["slug"] != "childcare-100k-threshold"], POSTS, RULES
    )
    link = "policyengine.org/uk/childcare-100k-threshold"
    assert cmp.check_edition("e.html", link, PUSH, reg, index(STALE_CHILDCARE))
    assert cmp.check_edition("e.html", link, PUSH, reg, index(FRESH_CHILDCARE)) == []
    assert cmp.check_edition("e.html", link, PUSH, reg, index({})) == []


def test_a_stale_alias_table_fails_the_check():
    reg = cmp.Registry([a for a in APPS if a["slug"] != "aca-calc"], POSTS, RULES)
    assert reg.stale_aliases() == ["us/aca-reforms-calculator -> us/aca-calc"]


# --- freshness: the scorecard's rule ---


def test_fresh_agrees_with_the_scorecards_cases():
    cases = json.loads((FIXTURES / "comparables_fresh_cases.json").read_text())
    assert len(cases) > 50
    for case in cases:
        assert (cmp.fresh(case["entry"], case["on"], case["window"]) == []) == case[
            "fresh"
        ], case


def test_a_pending_gap_with_no_found_on_counts_as_found():
    entry = record("app", "x", [PUSH])
    entry["comparisons"] = [{"claim": "c", "status": "pending"}]
    assert cmp.fresh(entry, PUSH, WINDOW)


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
    idx = dict(
        index({"analysis-uk-childcare-100k-threshold": rec}),
        promotion_window_days=window,
    )
    errors = cmp.check_edition(
        "e.html", "policyengine.org/uk/childcare-100k-threshold", PUSH, registry(), idx
    )
    in_window = any(-window <= o <= 0 for o in offsets)
    blocked = pending is not None and pending <= 0
    assert (errors == []) == (in_window and not blocked)


def test_a_search_against_old_results_is_not_fresh():
    rec = record("app", "childcare-100k-threshold", [PUSH], pins_match=False)
    errors = cmp.check_edition(
        "e.html",
        "policyengine.org/uk/childcare-100k-threshold",
        PUSH,
        registry(),
        index({"analysis-uk-childcare-100k-threshold": rec}),
    )
    assert errors and "compared the results the page reads now" in errors[0]


# --- the index's shape ---


def good_index():
    return index(FRESH_CHILDCARE)


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
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"].update(
            searches=None
        ),
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"].update(
            searches=[]
        ),
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"]["searches"][
            0
        ].update(date="soon"),
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"]["searches"][
            0
        ].pop("results_pins"),
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"].pop(
            "current_pins"
        ),
        lambda i: i["analyses"]["analysis-uk-childcare-100k-threshold"].update(
            comparisons=[{"claim": "c"}]
        ),
    ],
)
def test_an_index_of_the_wrong_shape_fails_with_a_message(breaks, tmp_path):
    idx = good_index()
    breaks(idx)
    assert cmp.check_index(idx)
    path = tmp_path / "index.json"
    path.write_text(json.dumps(idx))
    edition = tmp_path / f"{PUSH}-uk.html"
    edition.write_text("policyengine.org/uk/childcare-100k-threshold", encoding="utf-8")
    due, errors = cmp.run_check([edition], index_source=str(path), cutover="2026-10-26")
    assert due == [edition] and errors


def test_a_good_index_passes():
    assert cmp.check_index(good_index()) == []


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
    ):
        (tmp_path / name).write_text(json.dumps(data))
    return dict(
        apps=str(tmp_path / "apps.json"),
        posts=str(tmp_path / "posts.json"),
        index_source=str(tmp_path / "index.json"),
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
    monkeypatch.setattr(cmp, "today_utc", lambda: "2026-11-30")
    path = make_edition(tmp_path, "2026-10-01-uk.html")
    result, client = upload(path, mocker)
    assert result.exit_code == 1
    client.assert_not_called()
