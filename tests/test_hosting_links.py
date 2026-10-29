"""Tests for the hosting-address check."""

from pathlib import Path
from urllib.parse import quote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from newsletter_uploader import hosting_links
from newsletter_uploader.hosting_links import (
    HOSTING_DOMAINS,
    HostingLinkError,
    check_no_hosting_links,
    find_hosting_links,
    is_hosting_host,
    main,
)

EDITIONS = Path(__file__).resolve().parent.parent / "editions"


def link(url, text="See the dashboard"):
    return f'<a href="{url}" style="color:#319795;">{text}</a>'


@pytest.mark.parametrize(
    "host",
    [
        "ballot-measures-2026.vercel.app",
        "uk-autumn-budget-dashboard-git-dev-policy-engine.vercel.app",
        "vercel.app",
        "vercel.com",
        "BALLOT-MEASURES-2026.Vercel.App",
        "some-site.netlify.app",
        "preview.pages.dev",
        "policyengine--household-api.modal.run",
        "api-abc123-uc.a.run.app",
        "policyengine.appspot.com",
        "policyengine.github.io",
    ],
)
def test_hosting_hosts_are_flagged(host):
    assert is_hosting_host(host)
    hits = find_hosting_links(link(f"https://{host}/us/page"))
    assert hits == [(1, host.lower())]


@pytest.mark.parametrize(
    "host",
    [
        "policyengine.org",
        "www.policyengine.org",
        "app.policyengine.org",
        "legacy.policyengine.org",
        "raw.githubusercontent.com",
        "github.com",
        "fhoces.github.io",
        "notvercel.app",
        "vercel.app.example.com",
        "myvercel.com",
        "axiom.org",
    ],
)
def test_other_hosts_pass(host):
    assert not is_hosting_host(host)
    assert find_hosting_links(link(f"https://{host}/us/page")) == []


@pytest.mark.parametrize(
    "html, host",
    [
        # The address in link text, with no scheme.
        (
            "<p>Try ballot-measures-2026.vercel.app/us/ballot-measures-2026</p>",
            "ballot-measures-2026.vercel.app",
        ),
        # Inside another URL's query string, percent-encoded.
        (
            link(
                "https://www.policyengine.org/r?to="
                + quote("https://x.vercel.app/a", safe="")
            ),
            "x.vercel.app",
        ),
        # HTML entities for the dots.
        (link("https://x&#46;vercel&#x2E;app/a"), "x.vercel.app"),
        # An image src.
        ('<img src="https://x.vercel.app/og.png" alt="Chart">', "x.vercel.app"),
        # Single-quoted and unquoted attributes.
        ("<a href='https://x.vercel.app/'>a</a>", "x.vercel.app"),
        ("<a href=https://x.vercel.app/>a</a>", "x.vercel.app"),
    ],
)
def test_hosts_count_wherever_a_reader_could_see_or_follow_them(html, host):
    assert find_hosting_links(html) == [(1, host)]


def test_plain_mentions_of_vercel_pass():
    html = "<p>We host dashboards on Vercel and Modal, and the API on Cloud Run.</p>"
    assert find_hosting_links(html) == []


def test_reports_line_numbers_and_every_hit():
    html = "\n".join(
        [
            "<html><body>",
            link("https://www.policyengine.org/us/ballot-measures-2026"),
            link("https://a.vercel.app/") + " " + link("https://b.modal.run/"),
            "</body></html>",
        ]
    )
    assert find_hosting_links(html) == [(3, "a.vercel.app"), (3, "b.modal.run")]


def test_allowed_hosts_are_reviewed_exceptions(monkeypatch):
    monkeypatch.setattr(hosting_links, "ALLOWED_HOSTS", ("partner.vercel.app",))
    assert find_hosting_links(link("https://partner.vercel.app/")) == []
    assert find_hosting_links(link("https://other.vercel.app/")) == [
        (1, "other.vercel.app")
    ]


def test_check_raises_with_each_hit_and_the_fix():
    html = "<p>x</p>\n" + link("https://ballot-measures-2026.vercel.app/us/x")
    with pytest.raises(HostingLinkError) as raised:
        check_no_hosting_links(html, source="2026-11-03-us.html")
    message = str(raised.value)
    assert "2026-11-03-us.html" in message
    assert "line 2: ballot-measures-2026.vercel.app" in message
    assert "policyengine.org" in message
    assert "appZoneRoutes.ts" in message


def test_check_passes_clean_html():
    check_no_hosting_links(link("https://www.policyengine.org/us/x"))


def test_main_prints_hits_and_returns_status(tmp_path, capsys):
    clean = tmp_path / "clean.html"
    clean.write_text(link("https://www.policyengine.org/"))
    dirty = tmp_path / "dirty.html"
    dirty.write_text("<p>a</p>\n" + link("https://x.vercel.app/"))
    assert main([str(clean)]) == 0
    assert capsys.readouterr().out == ""
    assert main([str(clean), str(dirty)]) == 1
    assert capsys.readouterr().out == "2:x.vercel.app\n"


# The real editions: what went out, so what the check must catch.


def test_sent_29_october_us_edition_has_its_vercel_links_caught():
    html = (EDITIONS / "2026-10-29-us.html").read_text(encoding="utf-8")
    hosts = [host for _, host in find_hosting_links(html)]
    assert hosts.count("ballot-measures-2026.vercel.app") == html.count(
        "ballot-measures-2026.vercel.app"
    )
    assert "fhoces.github.io" not in hosts


@pytest.mark.parametrize(
    "edition, host",
    [
        (
            "2025-11-25-uk.html",
            "uk-autumn-budget-dashboard-git-dev-policy-engine.vercel.app",
        ),
        ("2026-03-18-us.html", "policyengine.github.io"),
        ("2026-04-01-us.html", "april-fools-2026-two.vercel.app"),
    ],
)
def test_earlier_editions_with_hosting_links_are_caught(edition, host):
    html = (EDITIONS / edition).read_text(encoding="utf-8")
    assert host in [h for _, h in find_hosting_links(html)]


# Properties over generated hosts and surrounding text.

LABEL = st.from_regex(r"[a-z0-9](?:[a-z0-9-]{0,14}[a-z0-9])?", fullmatch=True)
TEXT = st.text(
    alphabet=st.sampled_from(list("abcdefghij XYZ,;:!()0123456789")), max_size=40
)


@st.composite
def hosting_hosts(draw):
    labels = draw(st.lists(LABEL, min_size=0, max_size=3))
    return ".".join(labels + [draw(st.sampled_from(HOSTING_DOMAINS))])


@st.composite
def other_hosts(draw):
    labels = draw(st.lists(LABEL, min_size=1, max_size=3))
    tld = draw(st.sampled_from(["org", "com", "io", "uk", "net", "dev", "app"]))
    return ".".join(labels + [tld])


@given(host=hosting_hosts(), before=TEXT, after=TEXT, path=LABEL)
def test_property_any_hosting_host_in_any_text_is_caught(host, before, after, path):
    html = f"<p>{before}{link(f'https://{host}/{path}')}{after}</p>"
    assert host in [h for _, h in find_hosting_links(html)]


@given(host=hosting_hosts(), path=LABEL)
def test_property_encoding_never_hides_a_host(host, path):
    url = f"https://{host}/{path}"
    percent = link("https://www.policyengine.org/r?to=" + quote(url, safe=""))
    entities = link("".join(f"&#{ord(c)};" for c in url))
    for html in (percent, entities):
        assert host in [h for _, h in find_hosting_links(html)]


@given(host=other_hosts(), before=TEXT, after=TEXT, path=LABEL)
def test_property_other_hosts_are_never_flagged(host, before, after, path):
    if is_hosting_host(host):
        return
    html = f"<p>{before}{link(f'https://{host}/{path}')}{after}</p>"
    assert find_hosting_links(html) == []


@given(
    lines=st.lists(TEXT, min_size=1, max_size=8),
    index=st.integers(min_value=0, max_value=7),
    host=hosting_hosts(),
)
def test_property_reported_line_is_the_line_the_link_sits_on(lines, index, host):
    index = index % len(lines)
    lines = list(lines)
    lines[index] = lines[index] + link(f"https://{host}/")
    assert find_hosting_links("\n".join(lines)) == [(index + 1, host)]
