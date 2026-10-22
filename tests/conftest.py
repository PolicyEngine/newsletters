"""Pytest configuration and shared fixtures."""

import json

import pytest

from newsletter_uploader import comparables


@pytest.fixture(autouse=True)
def offline_comparables(tmp_path_factory, monkeypatch):
    """The comparables check reads local, empty registries and a valid empty
    index, so no test reaches the network; tests that need data pass their
    own sources."""
    root = tmp_path_factory.mktemp("comparables-sources")
    (root / "apps.json").write_text("[]")
    (root / "posts.json").write_text("[]")
    (root / "index.json").write_text(
        json.dumps(
            {
                "schema": comparables.INDEX_SCHEMA,
                "promotion_window_days": 7,
                "entry_rules": {
                    "analysis_tags": ["policy"],
                    "no_estimate_tags": ["event"],
                    "country_tags": ["uk", "us", "ca", "ng", "il"],
                    "default_country": "us",
                    "search_kinds": [
                        "prepublish",
                        "backfill",
                        "reharvest",
                        "prepromotion",
                    ],
                },
                "analyses": {},
            }
        )
    )
    monkeypatch.setattr(comparables, "APPS_URL", str(root / "apps.json"))
    monkeypatch.setattr(comparables, "POSTS_URL", str(root / "posts.json"))
    (root / "routes.json").write_text(
        json.dumps(
            {
                "schema": comparables.ROUTES_SCHEMA,
                "paths": [{"path": "/us/none", "prefix": True, "entry": "app us/none"}],
                "hosts": [],
            }
        )
    )
    monkeypatch.setattr(comparables, "INDEX_URL", str(root / "index.json"))
    monkeypatch.setattr(comparables, "ROUTES_URL", str(root / "routes.json"))


@pytest.fixture
def api_key():
    """Sample API key for testing."""
    return "test-key-us5"


@pytest.fixture
def list_id():
    """Sample list ID for testing."""
    return "test-list-id"
