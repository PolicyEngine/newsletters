"""Tests for the hosting-address check."""

import time
from pathlib import Path
from urllib.parse import quote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from newsletter_uploader import hosting_links
from newsletter_uploader.hosting_links import (
    HOSTING_DOMAINS,
    HOSTING_HOSTS,
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
        "theaxiomfoundation.github.io",
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


@pytest.mark.parametrize(
    "html",
    [
        # Browsers drop tabs and newlines anywhere in a URL.
        link("https://x.vercel.\napp/"),
        link("https://x.vercel.\r\napp/"),
        link("https://x.vercel.\tapp/"),
        # The same whitespace as entities or percent-escapes.
        link("https://x.vercel.&#10;app/"),
        link("https://x.vercel.&#x9;app/"),
        link("https://x.vercel.&NewLine;app/"),
        link("https://x.vercel.%0Aapp/"),
        "<a href=https://x.vercel.&#10;app/>a</a>",
        # Browsers read the ideographic and full-width stops as dots.
        link("https://x.vercel\u3002app/"),
        link("https://x.vercel\uff0eapp/"),
        link("https://x.vercel\uff61app/"),
        link("https://x.vercel%E3%80%82app/"),
        # Full-width letters fold to ASCII; invisible characters drop out.
        link("https://x.\uff56\uff45\uff52\uff43\uff45\uff4c.app/"),
        link("https://x.ver\u200bcel.app/"),
        link("https://x.ver&shy;cel.app/"),
    ],
)
def test_hosts_count_after_the_folding_a_browser_does(html):
    assert find_hosting_links(html) == [(1, "x.vercel.app")]


@pytest.mark.parametrize(
    "host",
    [
        # Another domain whose leftmost labels happen to read vercel.app.
        "vercel.app\u3002example.org",
        "vercel.app.\u4f8b\u5b50.org",
        "vercel.app.\u4f8b\u5b50",
        "foo_vercel.app",
    ],
)
def test_hosts_that_only_start_like_a_hosting_domain_pass(host):
    assert not is_hosting_host(host)
    assert find_hosting_links(link(f"https://{host}/")) == []


@pytest.mark.parametrize(
    "html, host",
    [
        (link("https://\u4f8b\u5b50.vercel.app/"), "\u4f8b\u5b50.vercel.app"),
        (link("https://m\u00fcnchen.vercel.app/"), "m\u00fcnchen.vercel.app"),
        # Glued to text in another script, with no space or dot.
        ("<p>\u8bbf\u95eevercel.app\u4e86\u89e3</p>", "vercel.app"),
        ("<p>See...vercel.app</p>", "vercel.app"),
    ],
)
def test_hosts_in_other_scripts_are_read_whole(html, host):
    assert find_hosting_links(html) == [(1, host)]


def test_a_host_split_across_lines_reports_where_its_value_starts():
    html = "\n".join(
        [
            "<p>a</p>",
            '<img srcset="https://a.vercel.app/x.png 1x,',
            '  https://b.vercel.app/y.png 2x" alt="x">',
            link("https://c.vercel.\napp/"),
            "<p>d.vercel.app</p>",
        ]
    )
    assert find_hosting_links(html) == [
        (2, "a.vercel.app"),
        (2, "b.vercel.app"),
        (4, "c.vercel.app"),
        (6, "d.vercel.app"),
    ]


def test_a_space_or_a_sentence_break_ends_a_host():
    html = "<p>We host on Vercel. App users like it, and on Modal.\nRun it.</p>"
    assert find_hosting_links(html) == []
    assert find_hosting_links(link("https://x.vercel. app/")) == []


@pytest.mark.parametrize(
    "html, hits",
    [
        # Outside a URL attribute a line break stays a break between words, so
        # the host after it still counts...
        (
            '<img src="https://www.policyengine.org/a.png" '
            'alt="Our calculator at\npolicyengine.github.io/tanf">',
            [(2, "policyengine.github.io")],
        ),
        ('<img src="a.png" alt="Screenshot from\nvercel.com">', [(2, "vercel.com")]),
        ('<img src="a.png" alt="Preview at&#10;vercel.app">', [(1, "vercel.app")]),
        ('<p title="See\tvercel.app">a</p>', [(1, "vercel.app")]),
        (
            '--body="Hi Jane,\nThe preview lives at\npolicyengine.github.io/tanf"',
            [(3, "policyengine.github.io")],
        ),
        # ...and two words never join into a host.
        ('<img src="a.png" alt="We moved off Modal.\nRun the numbers">', []),
        # Attribute names are case-insensitive.
        ('<a HREF="https://x.vercel.&#10;app/">a</a>', [(1, "x.vercel.app")]),
        # A value that runs past a missing closing quote into the markup after it
        # doesn't join the lines it swallows.
        (
            '<a href="https://www.policyengine.org/x>broken\n'
            "<p>We left Modal.\nRun it.</p>\n"
            '<p class="note">x</p>',
            [],
        ),
    ],
)
def test_only_url_attributes_drop_line_breaks(html, hits):
    assert find_hosting_links(html) == hits


@given(
    word=st.from_regex(r"[A-Za-z]{1,8}", fullmatch=True),
    brk=st.sampled_from(["\n", "\t", "&#10;", "\r\n"]),
    host=st.sampled_from(HOSTING_DOMAINS + HOSTING_HOSTS),
    attr=st.sampled_from(["alt", "title", "aria-label", "class"]),
)
def test_property_a_host_after_a_line_break_in_any_attribute_is_caught(
    word, brk, host, attr
):
    html = (
        f'<img src="https://www.policyengine.org/a.png" {attr}="{word}{brk}{host}/x">'
    )
    assert host in [h for _, h in find_hosting_links(html)]


@pytest.mark.parametrize(
    "html, hosts",
    [
        # The text a reader sees runs on through inline tags.
        (link("https://www.policyengine.org/", "x.vercel<wbr>.app"), ["x.vercel.app"]),
        (link("https://x.vercel.app/", "x.vercel<wbr>.app"), ["x.vercel.app"]),
        (
            '<p>x.<span style="color:red">vercel</span>.app and '
            "<b>y</b>.netlify.app</p>",
            ["x.vercel.app", "y.netlify.app"],
        ),
        # A line break is not an inline tag.
        ("<p>see<br>vercel.app</p>", ["vercel.app"]),
        ("<p>vercel<br>.app</p>", []),
    ],
)
def test_hosts_split_by_inline_tags_are_read_as_shown(html, hosts):
    assert [h for _, h in find_hosting_links(html)] == hosts


@pytest.mark.parametrize(
    "html, host",
    [
        # Markdown emphasis around a host.
        ("<p>See _vercel.app_ now</p>", "vercel.app"),
        (
            "<p>See _policyengine.github.io/tanf_ for details</p>",
            "policyengine.github.io",
        ),
        ("<p>See __x.vercel.app__</p>", "x.vercel.app"),
    ],
)
def test_underscores_around_a_host_are_emphasis(html, host):
    assert find_hosting_links(html) == [(1, host)]


@pytest.mark.parametrize(
    "char",
    ["\u2064", "\u180e", "\u3164", "\uffa0", "\U0001d173", "\U000e0100", "\ufeff"],
)
def test_characters_a_hostname_ignores_drop_out(char):
    assert find_hosting_links(link(f"https://x.ver{char}cel.app/")) == [
        (1, "x.vercel.app")
    ]


def test_three_rounds_of_escaping_are_decoded():
    assert find_hosting_links("<p>x%25252Evercel%25252Eapp</p>") == [
        (1, "x.vercel.app")
    ]


def test_is_hosting_host_folds_the_host():
    assert is_hosting_host("x.vercel\u3002app")
    assert is_hosting_host("X.\uff36ercel.app")


def test_many_hits_on_one_line_stay_fast():
    started = time.perf_counter()
    hits = find_hosting_links(" ".join(["x.vercel.app"] * 20000))
    assert len(hits) == 20000
    # Comparing every hit with every other one took over 10 s here.
    assert time.perf_counter() - started < 5


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


@given(
    host=hosting_hosts(),
    before=TEXT,
    after=TEXT,
    left=st.sampled_from([" ", "(", ":", ";", "!", "/", "<br>", "\u3000"]),
    right=st.sampled_from([" ", ")", ",", ";", "!", "/", ". ", "<br>", "\u3000"]),
)
def test_property_a_host_in_running_text_is_caught(host, before, after, left, right):
    html = f"<p>{before}{left}{host}{right}{after}</p>"
    assert host in [h for _, h in find_hosting_links(html)]


@given(host=hosting_hosts(), path=LABEL)
def test_property_encoding_never_hides_a_host(host, path):
    url = f"https://{host}/{path}"
    percent = link("https://www.policyengine.org/r?to=" + quote(url, safe=""))
    entities = link("".join(f"&#{ord(c)};" for c in url))
    for html in (percent, entities):
        assert host in [h for _, h in find_hosting_links(html)]


@given(
    host=hosting_hosts(),
    path=LABEL,
    breaks=st.lists(
        st.sampled_from(["\n", "\r\n", "\t", "&#10;", "&#9;", "%0A"]), max_size=3
    ),
    dot=st.sampled_from([".", "\u3002", "\uff0e", "\uff61", "&#46;", "%2E"]),
    data=st.data(),
)
def test_property_whitespace_and_unicode_dots_never_hide_a_host(
    host, path, breaks, dot, data
):
    # Whole characters or escapes, so a break never lands inside an escape.
    url = [dot if char == "." else char for char in host]
    for brk in breaks:
        url.insert(data.draw(st.integers(0, len(url))), brk)
    html = "<p>a</p>\n" + link("https://" + "".join(url) + "/" + path)
    assert (2, host) in find_hosting_links(html)


@given(
    host=hosting_hosts(),
    tail=st.lists(
        st.text(alphabet="\u4f8b\u5b50\u00fcabc", min_size=1, max_size=5),
        min_size=1,
        max_size=2,
    ),
    tld=st.sampled_from(["org", "\u4e2d\u56fd", "com"]),
    dot=st.sampled_from([".", "\u3002"]),
)
def test_property_a_longer_host_that_starts_like_a_hosting_one_passes(
    host, tail, tld, dot
):
    longer = dot.join([host] + tail + [tld])
    if is_hosting_host(longer):
        return
    assert find_hosting_links(link(f"https://{longer}/")) == []


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
