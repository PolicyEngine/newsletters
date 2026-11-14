"""Regression cases for primary pages, browser URLs and shared deployments."""

import copy

import pytest

from newsletter_uploader import comparables as cmp
from tests.test_comparables import (
    APPS,
    POSTS,
    PUSH,
    ROUTE_MAP,
    RULES,
    app,
    host,
    index,
    record,
    route,
)


def resolver(apps=APPS, analyses=None, route_map=ROUTE_MAP):
    return cmp.Routes(
        route_map, cmp.Registry(apps, POSTS, RULES), index(analyses or {})
    )


def edition_errors(url, routes, analyses):
    return cmp.check_edition(
        "2026-11-02-us.html",
        f'<a href="{url}">Analysis</a>',
        PUSH,
        routes,
        index(analyses),
    )


def test_external_primary_page_with_no_deployments_retains_its_stale_record():
    url = "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold"
    analyses = {
        "analysis-uk-childcare-100k-threshold": {
            **record("app", "childcare-100k-threshold", ["2026-10-21"]),
            "url": url,
            "deployments": [],
        }
    }
    apps = [a for a in APPS if a["slug"] != "childcare-100k-threshold"]
    routes = resolver(apps, analyses, {"paths": [], "hosts": []})
    errors = edition_errors(url, routes, analyses)
    assert len(errors) == 1
    assert "no comparables search between" in errors[0]


@pytest.mark.parametrize(
    "url",
    [
        "https://reader@policyengine.org/uk/scottish-budget-2026-27",
        r"https://policyengine.org\uk\scottish-budget-2026-27",
        r"https://policyengine.org/uk\scottish-budget-2026-27",
        "https://policyengine.org/uk/\nscottish-budget-2026-27",
        "https://policyengine.org/uk/\tscottish-budget-2026-27",
        "https://policyengine.org/uk/\rscottish-budget-2026-27",
        "https://policyengine.org/uk/💡/../scottish-budget-2026-27",
        "https://policyengine。org/uk/scottish-budget-2026-27",
        "https://ＰＯＬＩＣＹＥＮＧＩＮＥ.org/uk/scottish-budget-2026-27",
        "https://policyengine.org/uk/%22/../scottish-budget-2026-27",
        "https://policyengine.org/uk/%20/../scottish-budget-2026-27",
        "https://policyengine.org/uk/%3f/../scottish-budget-2026-27",
        "https://policyengine.org/uk/%23/../scottish-budget-2026-27",
        "https%3A%2F%2Fpolicyengine.org%2Fuk%2Fscottish-budget-2026-27",
        "https%253A%252F%252Fpolicyengine.org%252Fuk%252Fscottish-budget-2026-27",
    ],
)
def test_browser_equivalent_anchor_destinations_require_the_missing_record(url):
    errors = edition_errors(url, resolver(), {})
    assert len(errors) == 1
    assert "analysis-uk-scottish-budget-2026-27" in errors[0]
    assert "has no comparables record" in errors[0]


@pytest.mark.parametrize("url", ["https://[", "https:/policyengine.org/uk/marriage"])
def test_unsupported_absolute_urls_are_explicitly_refused(url):
    errors = edition_errors(url, resolver(), {})
    assert len(errors) == 1
    assert "unsupported absolute link" in errors[0]


@pytest.mark.parametrize(
    "suffix, expected_country",
    [("", "us"), ("?country=us", "us"), ("?country=uk", "uk")],
)
@pytest.mark.parametrize("record_deployments", [False, True])
def test_country_queries_and_the_default_only_judge_the_selected_country(
    suffix, expected_country, record_deployments
):
    analyses = {
        "analysis-us-marriage": record("app", "marriage", [PUSH], country="us"),
        "analysis-uk-marriage": record("app", "marriage", ["2026-01-01"]),
    }
    if record_deployments:
        for country, record_query in (("us", ""), ("uk", "?country=uk")):
            analyses["analysis-" + country + "-marriage"]["deployments"] = [
                "https://marriage-zeta-beryl.vercel.app/us/marriage" + record_query
            ]
    url = "https://marriage-zeta-beryl.vercel.app/us/marriage" + suffix
    routes = resolver(analyses=analyses)
    errors = edition_errors(url, routes, analyses)
    canonical = edition_errors(
        "https://policyengine.org/" + expected_country + "/marriage", routes, analyses
    )
    assert errors == canonical
    assert bool(errors) == (expected_country == "uk")


@pytest.mark.parametrize("query", ["country=ca", "country=us&country=uk", "country="])
def test_unknown_or_conflicting_shared_country_selection_is_refused(query):
    _, refused = cmp.linked(
        "https://marriage-zeta-beryl.vercel.app/us/marriage?" + query, resolver()
    )
    assert len(refused) == 1
    assert "ambiguous deployment routing" in refused[0]


def shared_sources(delisted=False):
    analyses = {
        "analysis-uk-a": record(
            "app", "a", ["2026-01-01"], deployments=["https://shared.example/uk/a"]
        ),
        "analysis-us-b": record(
            "app",
            "b",
            [PUSH],
            country="us",
            deployments=["https://shared.example/us/b"],
        ),
    }
    apps = [app("uk", "a", "https://shared.example/uk/a")]
    routes = {
        "paths": [route("/uk/a", "app uk/a")],
        "hosts": [host("shared.example", ["app uk/a"], "/uk/a")],
    }
    if not delisted:
        apps.append(app("us", "b", "https://shared.example/us/b"))
        routes["paths"].append(route("/us/b", "app us/b"))
        routes["hosts"].append(host("shared.example", ["app us/b"], "/us/b"))
    return analyses, resolver(apps, analyses, routes)


@pytest.mark.parametrize("delisted", [False, True])
def test_record_deployments_preserve_shared_host_project_boundaries(delisted):
    analyses, routes = shared_sources(delisted)
    assert edition_errors("https://shared.example/us/b", routes, analyses) == []
    assert edition_errors("https://shared.example/us/b/details", routes, analyses) == []
    assert edition_errors("https://shared.example/unrelated", routes, analyses) == []
    errors = edition_errors("https://shared.example/uk/a", routes, analyses)
    assert len(errors) == 1
    assert "no comparables search between" in errors[0]


def test_record_ownership_narrows_an_artifact_whole_host_mapping():
    analyses, _ = shared_sources(delisted=True)
    routes = resolver(
        [app("uk", "a", "https://shared.example/uk/a")],
        analyses,
        {
            "paths": [route("/uk/a", "app uk/a")],
            "hosts": [host("shared.example", ["app uk/a"])],
        },
    )
    assert edition_errors("https://shared.example/us/b", routes, analyses) == []
    assert edition_errors("https://shared.example/unrelated", routes, analyses) == []


def test_an_app_and_its_record_count_as_one_host_owner():
    analyses = {
        "analysis-uk-childcare-100k-threshold": record(
            "app",
            "childcare-100k-threshold",
            ["2026-01-01"],
            deployments=[
                "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold"
            ],
        )
    }
    errors = edition_errors(
        "https://uk-childcare-100k-threshold.vercel.app/",
        resolver(analyses=analyses),
        analyses,
    )
    assert len(errors) == 1
    assert "no comparables search between" in errors[0]


def test_registry_sources_only_disambiguate_artifact_membership():
    route_map = copy.deepcopy(ROUTE_MAP)
    route_map["hosts"] = [h for h in route_map["hosts"] if "marriage" not in h["host"]]
    found, refused = cmp.linked(
        "https://marriage-zeta-beryl.vercel.app/us/marriage?country=uk",
        resolver(route_map=route_map),
    )
    assert found == refused == []
