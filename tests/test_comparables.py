"""Fresh comparables before a newsletter goes out (comparables.py).

Invariants:
- an edition dated before the cutover is never checked, and nothing is
  downloaded for it;
- a linked analysis that publishes an estimate passes exactly when the
  scorecard records a search in the window before the edition's date and no
  gap found by then is pending (checked over every offset and window in a grid,
  the finite-domain form of a property test);
- links to anything that is not such an analysis are never checked;
- the upload CLI refuses a stale edition before it touches Mailchimp.
"""

import datetime as dt
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from newsletter_uploader import comparables as cmp
from newsletter_uploader.cli import main as cli_main

EDITIONS = Path(__file__).resolve().parent.parent / "editions"
WINDOW = 7
PUSH = "2026-11-02"

APPS = [
    {
        "slug": "childcare-100k-threshold",
        "countryId": "uk",
        "displayWithResearch": True,
        "tags": ["uk", "featured", "policy", "interactives"],
    },
    {
        "slug": "marriage",
        "countryId": "uk",
        "displayWithResearch": True,
        "tags": ["uk", "policy"],
        "comparables": {"status": "no_estimate", "reason": "a household calculator"},
    },
    {"slug": "tool", "countryId": "us", "tags": ["us", "policy"]},
]
POSTS = [
    {"filename": "UK_Two_Child_Limit.md", "tags": ["uk", "policy"]},
    {"filename": "giving-tuesday.md", "tags": ["us", "giving"]},
]


def shift(date, days):
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def index_with(search_dates, pending_found=(), kind="app"):
    return {
        "schema": cmp.INDEX_SCHEMA,
        "promotion_window_days": WINDOW,
        "analyses": {
            "analysis-uk-childcare-100k-threshold": {
                "kind": kind,
                "searches": [{"date": d, "kind": "reharvest"} for d in search_dates],
                "comparisons": [
                    {"claim": f"c{i}", "status": "pending", "found_on": found}
                    for i, found in enumerate(pending_found)
                ],
            }
        },
    }


def edition(tmp_path, date, body):
    path = tmp_path / f"{date}-uk.html"
    path.write_text(f"<html><body>{body}</body></html>")
    return path


CHILDCARE_LINK = (
    '<a href="https://www.policyengine.org/uk/childcare-100k-threshold'
    '?utm_source=newsletter">dashboard</a>'
)


class TestLinks:
    def test_finds_apps_and_posts_once(self):
        text = (
            CHILDCARE_LINK
            + '<a href="https://policyengine.org/uk/childcare-100k-threshold/">x</a>'
            + '<a href="https://policyengine.org/uk/research/UK_Two_Child_Limit#top">'
            + "post</a> https://policyengine.org/us/research/giving-tuesday."
        )
        assert cmp.analysis_links(text) == [
            ("uk", "app", "childcare-100k-threshold"),
            ("uk", "post", "uk-two-child-limit"),
            ("us", "post", "giving-tuesday"),
        ]

    def test_ignores_other_hosts_and_bare_country_pages(self):
        text = (
            '<a href="https://app.policyengine.org/uk/reports">calc</a>'
            '<a href="https://www.policyengine.org/uk">home</a>'
            '<a href="https://example.org/uk/childcare-100k-threshold">other</a>'
        )
        assert cmp.analysis_links(text) == []

    def test_post_slug_matches_the_website(self):
        assert cmp.post_slug("UK_Two_Child_Limit.md") == "uk-two-child-limit"


class TestRegistry:
    def test_research_entries_are_listed_apps_and_posts_by_country(self):
        entries = cmp.research_entries(APPS, POSTS)
        assert ("uk", "app", "childcare-100k-threshold") in entries
        assert ("us", "app", "tool") not in entries  # not listed with research
        assert ("uk", "post", "uk-two-child-limit") in entries

    def test_what_publishes_an_estimate(self):
        entries = cmp.research_entries(APPS, POSTS)
        assert cmp.publishes_estimate(
            entries[("uk", "app", "childcare-100k-threshold")]
        )
        assert not cmp.publishes_estimate(entries[("uk", "app", "marriage")])
        assert not cmp.publishes_estimate(entries[("us", "post", "giving-tuesday")])


class TestFresh:
    @pytest.mark.parametrize("window", [1, 3, 7, 14])
    def test_fresh_exactly_when_a_search_falls_in_the_window(self, window):
        for offset in range(-20, 6):
            searches = [shift(PUSH, offset)]
            in_window = -window <= offset <= 0
            assert (
                cmp.fresh(
                    index_with(searches)["analyses"][
                        "analysis-uk-childcare-100k-threshold"
                    ],
                    PUSH,
                    window,
                )
                == []
            ) == in_window, (window, offset)

    def test_a_wider_window_is_never_stricter(self):
        for offset in range(-20, 6):
            entry = index_with([shift(PUSH, offset)])["analyses"][
                "analysis-uk-childcare-100k-threshold"
            ]
            for narrow in range(1, 15):
                for wide in range(narrow, 15):
                    if cmp.fresh(entry, PUSH, narrow) == []:
                        assert cmp.fresh(entry, PUSH, wide) == []

    def test_a_pending_gap_blocks_only_once_found(self):
        for offset in range(-10, 6):
            entry = index_with([PUSH], pending_found=[shift(PUSH, offset)])["analyses"][
                "analysis-uk-childcare-100k-threshold"
            ]
            assert bool(cmp.fresh(entry, PUSH, WINDOW)) == (offset <= 0)


class TestEdition:
    def check(self, tmp_path, body, index):
        path = edition(tmp_path, PUSH, body)
        return cmp.check_edition(
            path, path.read_text(), cmp.research_entries(APPS, POSTS), index
        )

    def test_fresh_record_passes(self, tmp_path):
        assert self.check(tmp_path, CHILDCARE_LINK, index_with([shift(PUSH, -2)])) == []

    def test_stale_record_fails(self, tmp_path):
        errors = self.check(tmp_path, CHILDCARE_LINK, index_with([shift(PUSH, -12)]))
        assert len(errors) == 1
        assert "run a prepromotion search" in errors[0]

    def test_missing_record_fails(self, tmp_path):
        index = index_with([PUSH])
        index["analyses"] = {}
        errors = self.check(tmp_path, CHILDCARE_LINK, index)
        assert "has no comparables record" in errors[0]

    def test_a_record_of_another_kind_does_not_count(self, tmp_path):
        errors = self.check(tmp_path, CHILDCARE_LINK, index_with([PUSH], kind="post"))
        assert "has no comparables record" in errors[0]

    def test_links_without_an_estimate_are_not_checked(self, tmp_path):
        body = (
            '<a href="https://policyengine.org/uk/marriage">calc</a>'
            '<a href="https://policyengine.org/us/research/giving-tuesday">post</a>'
            '<a href="https://policyengine.org/us/tool">tool</a>'
        )
        index = index_with([])
        index["analyses"] = {}
        assert self.check(tmp_path, body, index) == []

    def test_a_policy_post_needs_a_record(self, tmp_path):
        body = '<a href="https://policyengine.org/uk/research/uk-two-child-limit">p</a>'
        errors = self.check(tmp_path, body, index_with([PUSH]))
        assert "analysis-uk-uk-two-child-limit" in errors[0]

    def test_an_undated_file_is_reported(self, tmp_path):
        path = tmp_path / "draft.html"
        path.write_text(CHILDCARE_LINK)
        errors = cmp.check_edition(path, path.read_text(), {}, index_with([PUSH]))
        assert "no YYYY-MM-DD date" in errors[0]


class TestRun:
    def write_sources(self, tmp_path, index):
        apps, posts, idx = (tmp_path / n for n in ("apps.json", "posts.json", "i.json"))
        apps.write_text(json.dumps(APPS))
        posts.write_text(json.dumps(POSTS))
        idx.write_text(json.dumps(index))
        return str(apps), str(posts), str(idx)

    def test_nothing_before_the_cutover_is_checked_or_downloaded(self, tmp_path):
        old = edition(tmp_path, shift(cmp.PROMOTION_CUTOVER_DATE, -1), CHILDCARE_LINK)
        due, errors = cmp.run_check(
            [old], "/nonexistent/apps", "/nonexistent/posts", "/nonexistent/index"
        )
        assert (due, errors) == ([], [])

    def test_the_archive_is_never_checked(self):
        archive = [p for p in EDITIONS.iterdir() if p.suffix in (".html", ".md")]
        due = cmp.editions_to_check(archive, cmp.PROMOTION_CUTOVER_DATE)
        assert all(cmp.edition_date(p) >= cmp.PROMOTION_CUTOVER_DATE for p in due), due

    def test_main_passes_and_fails(self, tmp_path, capsys):
        path = edition(tmp_path, PUSH, CHILDCARE_LINK)
        ok = self.write_sources(tmp_path, index_with([PUSH]))
        argv = [str(path), "--apps", ok[0], "--posts", ok[1], "--index", ok[2]]
        assert cmp.main(argv + ["--cutover", "2026-10-26"]) == 0
        stale = self.write_sources(tmp_path, index_with([shift(PUSH, -30)]))
        argv = [str(path), "--apps", stale[0], "--posts", stale[1], "--index", stale[2]]
        assert cmp.main(argv + ["--cutover", "2026-10-26"]) == 1
        assert "prepromotion" in capsys.readouterr().out

    def test_a_wrong_index_schema_fails(self, tmp_path):
        path = edition(tmp_path, PUSH, CHILDCARE_LINK)
        index = index_with([PUSH])
        index["schema"] = "something/else"
        sources = self.write_sources(tmp_path, index)
        due, errors = cmp.run_check([path], *sources, cutover="2026-10-26")
        assert due and "is not comparables/index/1" in errors[0]

    def test_an_unreadable_source_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cmp.time, "sleep", lambda _s: None)
        path = edition(tmp_path, PUSH, CHILDCARE_LINK)
        with pytest.raises(SystemExit, match="could not read"):
            cmp.run_check(
                [path],
                index_source="https://127.0.0.1:9/index.json",
                cutover="2026-10-26",
            )


class TestUploadRefusesStaleEditions:
    def test_upload_stops_before_mailchimp(self, tmp_path, mocker):
        path = edition(tmp_path, PUSH, CHILDCARE_LINK)
        mocker.patch.object(cmp, "PROMOTION_CUTOVER_DATE", "2026-10-26")
        sources = {
            cmp.APPS_URL: APPS,
            cmp.POSTS_URL: POSTS,
            cmp.INDEX_URL: index_with([shift(PUSH, -30)]),
        }
        mocker.patch.object(cmp, "_load", side_effect=lambda where: sources[where])
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
                "key-us5",
            ],
        )
        assert result.exit_code == 1
        assert "Comparables are not fresh" in result.output
        client.assert_not_called()
