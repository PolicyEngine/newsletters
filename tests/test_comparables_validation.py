"""Downloaded source artifacts must fail closed before routing editions."""

import copy
import json

import pytest

from newsletter_uploader import comparables as cmp

PUSH = "2026-11-02"
CHILDCARE = "analysis-uk-childcare-100k-threshold"
RULES = {
    "analysis_tags": ["policy"],
    "no_estimate_tags": ["event"],
    "country_tags": ["uk", "us"],
    "default_country": "us",
}
APPS = [
    {
        "slug": "bill-tracker",
        "countryId": "us",
        "tags": ["us", "policy"],
        "displayWithResearch": True,
        "source": "https://tracker.example/us/bill-tracker?embedded=true",
    }
]
POSTS = [{"filename": "example-post.md", "tags": ["us", "policy"]}]
ROUTES = {
    "schema": cmp.ROUTES_SCHEMA,
    "paths": [
        {"path": "/us/bill-tracker", "prefix": True, "entry": "app us/bill-tracker"}
    ],
    "hosts": [
        {
            "host": "tracker.example",
            "pathPrefix": "/",
            "entries": ["app us/bill-tracker"],
        }
    ],
}
INDEX = {
    "schema": cmp.INDEX_SCHEMA,
    "promotion_window_days": 7,
    "entry_rules": RULES,
    "analyses": {
        CHILDCARE: {
            "kind": "app",
            "slug": "childcare-100k-threshold",
            "url": "https://policyengine.org/uk/childcare-100k-threshold",
            "deployments": [
                "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold"
            ],
            "current_pins": [],
            "searches": [{"date": "2026-10-21", "results_pins": []}],
            "comparisons": [],
        }
    },
}


def source_files(tmp_path):
    sources = {}
    for name, value in (
        ("apps", APPS),
        ("posts", POSTS),
        ("routes", ROUTES),
        ("index", INDEX),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        sources[name] = path
    return sources


def cli_args(tmp_path, sources, link="policyengine.org/us/bill-tracker"):
    edition = tmp_path / f"{PUSH}-us.html"
    edition.write_text(f'<a href="{link}">Analysis</a>', encoding="utf-8")
    return [
        str(edition),
        "--require-dates",
        *(part for name, path in sources.items() for part in (f"--{name}", str(path))),
    ]


@pytest.mark.parametrize(
    "field,value,problem,link",
    [
        (
            "url",
            "",
            "page url",
            "policyengine.org/uk/childcare-100k-threshold",
        ),
        (
            "deployments",
            ["not-a-url"],
            "deployments",
            "https://uk-childcare-100k-threshold.vercel.app/uk/childcare-100k-threshold",
        ),
        ("url", "https://[", "page url", "https://example.com"),
        ("url", "http://policyengine.org/uk/childcare", "page url", "example.com"),
        ("url", "https://", "page url", "example.com"),
        ("url", "https://bad host.example/childcare", "page url", "example.com"),
        ("url", "https://example.com:invalid/childcare", "page url", "example.com"),
        ("url", "https://example.com:70000/childcare", "page url", "example.com"),
        ("deployments", ["https://["], "deployments", "example.com"),
    ],
)
def test_invalid_index_urls_fail_the_cli_before_routes_disappear_or_raise(
    tmp_path, capsys, field, value, problem, link
):
    sources = source_files(tmp_path)
    index = copy.deepcopy(INDEX)
    index["analyses"][CHILDCARE][field] = value
    assert cmp.check_index(index)
    sources["index"].write_text(json.dumps(index), encoding="utf-8")

    assert cmp.main(cli_args(tmp_path, sources, link)) == 1
    output = capsys.readouterr().out
    assert "the scorecard index" in output and problem in output
    assert "ok   " not in output and "Traceback" not in output


@pytest.mark.parametrize(
    "change",
    [
        {"entry": "bill-tracker"},
        {"entry": "app us/bill-traker"},
        {"path": "/US/BILL-TRACKER"},
        {"path": "/us/%62ill-tracker"},
        {"path": "/us/./bill-tracker"},
        {"path": "/us/bill-tracker;"},
        {"path": "/us/bill:tracker"},
    ],
)
def test_invalid_route_paths_and_targets_fail_loading_instead_of_losing_an_app(
    tmp_path, capsys, change
):
    sources = source_files(tmp_path)
    routes = copy.deepcopy(ROUTES)
    routes["paths"][0].update(change)
    registry = cmp.Registry(APPS, POSTS, RULES)
    assert cmp.check_routes(routes, registry)
    sources["routes"].write_text(json.dumps(routes), encoding="utf-8")

    assert cmp.main(cli_args(tmp_path, sources)) == 1
    output = capsys.readouterr().out
    assert "route map" in output
    assert "ok   " not in output and "no comparables record" not in output


@pytest.mark.parametrize(
    "change",
    [
        {"host": "TRACKER.example"},
        {"host": "https://tracker.example"},
        {"host": "bad host.example"},
        {"pathPrefix": "us/bill-tracker"},
        {"pathPrefix": "/US/BILL-TRACKER"},
        {"pathPrefix": "/us/bill-tracker;"},
        {"pathPrefix": "/us/bill:tracker"},
        {"entries": ["bill-tracker"]},
        {"entries": ["app us/bill-traker"]},
    ],
)
def test_invalid_route_hosts_and_prefixes_fail_loading(tmp_path, capsys, change):
    sources = source_files(tmp_path)
    routes = copy.deepcopy(ROUTES)
    routes["hosts"][0].update(change)
    assert cmp.check_routes(routes, cmp.Registry(APPS, POSTS, RULES))
    sources["routes"].write_text(json.dumps(routes), encoding="utf-8")

    assert cmp.main(cli_args(tmp_path, sources)) == 1
    assert "route map" in capsys.readouterr().out


@pytest.mark.parametrize(
    "name,value",
    [
        ("apps", {}),
        ("posts", {}),
        ("apps", [None]),
        ("posts", ["example-post.md"]),
        ("apps", [{**APPS[0], "slug": None}]),
        ("apps", [{**APPS[0], "countryId": ["us"]}]),
        ("apps", [{**APPS[0], "tags": "policy"}]),
        ("apps", [{**APPS[0], "displayWithResearch": "false"}]),
        ("apps", [{**APPS[0], "source": "https://["}]),
        ("apps", [{**APPS[0], "comparables": []}]),
        ("posts", [{**POSTS[0], "filename": None}]),
        ("posts", [{**POSTS[0], "tags": ["us", 1]}]),
        ("posts", [{**POSTS[0], "comparables": {"scorecardSource": []}}]),
    ],
)
def test_wrong_registry_shapes_fail_before_constructing_the_registry(
    tmp_path, capsys, name, value
):
    sources = source_files(tmp_path)
    sources[name].write_text(json.dumps(value), encoding="utf-8")

    assert cmp.main(cli_args(tmp_path, sources)) == 1
    output = capsys.readouterr().out
    assert f"{name} registry" in output
    assert "ok   " not in output and "Traceback" not in output


def test_a_valid_empty_apps_array_cannot_erase_route_references(tmp_path, capsys):
    sources = source_files(tmp_path)
    sources["apps"].write_text("[]", encoding="utf-8")

    assert cmp.main(cli_args(tmp_path, sources)) == 1
    output = capsys.readouterr().out
    assert "missing registry entries: app us/bill-tracker" in output


def test_valid_registry_fields_and_consistent_references_pass_validation():
    apps = copy.deepcopy(APPS)
    apps.append(
        {
            "slug": "embedded-app",
            "countryId": "us",
            "source": "/us/embedded-app/embed",
            "tags": ["policy"],
        }
    )
    apps.append({"slug": "no-source-app", "countryId": "uk", "tags": []})
    assert cmp.check_registries(apps, POSTS) == []
    assert cmp.check_index(INDEX) == []
    assert cmp.check_routes(ROUTES, cmp.Registry(apps, POSTS, RULES)) == []


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/page?country=uk",
        "https://example.com:443/page",
        "https://[2001:db8::1]/page",
        "https://xn--bcher-kva.example/page",
    ],
)
def test_valid_https_pages_pass_index_validation(url):
    index = copy.deepcopy(INDEX)
    index["analyses"][CHILDCARE].update(url=url, deployments=[url])
    assert cmp.check_index(index) == []
