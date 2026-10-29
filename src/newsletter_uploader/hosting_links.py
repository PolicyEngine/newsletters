"""Find hosting addresses that must never reach subscribers.

Public links go to policyengine.org, never to the address of the platform that
hosts a page (Max, 2026-10-29: "never share vercel links publicly - should
always be on policyengine.org, esp in newsletters"). A sent email can't be
corrected, and a hosting address can change with the next deploy.

The check reads the raw HTML line by line, after decoding HTML entities and
percent-escapes, so a host counts wherever a subscriber or their email client
could see or follow it: an href, an image src, link text, or a URL inside
another URL's query string. It folds each host the way a browser does first:
tabs and newlines inside an attribute value drop out, and Unicode dots,
full-width letters and invisible characters fold to plain ASCII.

Run as a script, it prints `line:host` for each hit and exits 1 if it finds any.
lint-newsletters.sh runs it that way, with src/ on PYTHONPATH.
"""

import html
import re
import sys
import unicodedata
from typing import List, Tuple
from urllib.parse import unquote

# Every address under these domains belongs to a hosting platform: Vercel,
# Netlify, Cloudflare Pages, Modal, Cloud Run and App Engine.
HOSTING_DOMAINS = (
    "vercel.app",
    "vercel.com",
    "netlify.app",
    "pages.dev",
    "modal.run",
    "run.app",
    "appspot.com",
)

# GitHub Pages sites of our own. Other people's github.io sites are their
# canonical addresses, so they stay linkable.
HOSTING_HOSTS = ("policyengine.github.io",)

# Reviewed exceptions: exact hosts that may appear despite the lists above.
ALLOWED_HOSTS: Tuple[str, ...] = ()

# A host is two or more labels joined by dots. A label is any run of Unicode
# letters, digits, underscores and hyphens, so a host such as
# vercel.app.例子.org is read whole rather than cut short at vercel.app. The
# lookbehind stops a match starting inside a longer host or word.
HOST = re.compile(r"(?<![\w.-])((?:[\w-]+\.)+[\w-]+)(?![\w-])")

# The same with ASCII labels only, for an address glued to text in another
# script with no space, as in 访问vercel.app了解. A dot followed by a letter
# on either side means the host goes on, so it is left to HOST.
ASCII_HOST = re.compile(
    r"(?<![A-Za-z0-9_-])(?<!\w\.)"
    r"((?:[A-Za-z0-9_-]+\.)+[A-Za-z0-9_-]+)"
    r"(?![A-Za-z0-9_-])(?!\.\w)"
)

# A quoted or unquoted attribute value, such as an href or src.
ATTRIBUTE = re.compile(r"""(=\s*)(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""")

# Browsers drop tabs and newlines anywhere in a URL (WHATWG URL standard).
URL_WHITESPACE = re.compile("[\t\n\r]")

# Browsers read these as the dot between labels (UTS #46).
DOTS = re.compile("[\u3002\uff0e\uff61]")

# Characters a hostname drops (stringprep table B.1): soft hyphen, zero-width
# spaces and joiners, variation selectors and the byte order mark.
IGNORED = re.compile(
    "[\u00ad\u034f\u1806\u180b-\u180d\u200b-\u200d\u2060\ufe00-\ufe0f\ufeff]"
)


class HostingLinkError(ValueError):
    """Raised when newsletter HTML carries a hosting address."""


def is_hosting_host(host: str) -> bool:
    """Return True if a subscriber must never see this host."""
    host = _fold(host).lower().rstrip(".")
    if host in ALLOWED_HOSTS:
        return False
    if host in HOSTING_HOSTS:
        return True
    return any(
        host == domain or host.endswith("." + domain) for domain in HOSTING_DOMAINS
    )


def _decode(text: str) -> str:
    """Decode HTML entities, then percent-escapes, until the text stops changing."""
    for _ in range(3):
        decoded = unquote(html.unescape(text))
        if decoded == text:
            break
        text = decoded
    return text


def _fold(text: str) -> str:
    """Fold text the way a browser folds a hostname, to plain ASCII where it can.

    NFKC turns full-width and other compatibility forms into their plain
    letters, digits and dots; the ideographic full stops become dots; and
    invisible characters drop out.
    """
    return IGNORED.sub("", DOTS.sub(".", unicodedata.normalize("NFKC", text)))


def _join_attribute_values(content: str) -> str:
    """Decode each attribute value and drop its tabs and newlines.

    A browser follows https://x.vercel.<newline>app to x.vercel.app, so the
    check must read it that way too. Each raw newline removed goes back after
    the value, so every line outside the value keeps its number, and a host
    inside a value that spans lines reports the line where the value starts.
    """

    def join(match: "re.Match[str]") -> str:
        prefix, double, single, bare = match.groups()
        raw = next(value for value in (double, single, bare) if value is not None)
        quote = '"' if double is not None else "'" if single is not None else ""
        value = URL_WHITESPACE.sub("", _decode(raw))
        return prefix + quote + value + quote + "\n" * raw.count("\n")

    return ATTRIBUTE.sub(join, content)


def _hosting_hosts_in(text: str) -> List[str]:
    """Return the hosting hosts in one line of folded text, in order.

    When both patterns flag a host, as with münchen.vercel.app and its ASCII
    tail nchen.vercel.app, only the longer, enclosing match counts.
    """
    found = {}
    for pattern in (HOST, ASCII_HOST):
        for match in pattern.finditer(text):
            host = match.group(1).lower()
            if is_hosting_host(host):
                found[match.span(1)] = host
    spans = sorted(found)
    return [
        found[span]
        for span in spans
        if not any(
            other != span and other[0] <= span[0] and span[1] <= other[1]
            for other in spans
        )
    ]


def find_hosting_links(content: str) -> List[Tuple[int, str]]:
    """Return (line number, host) for each hosting address in the content."""
    lines = _join_attribute_values(content).split("\n")
    return [
        (number, host)
        for number, line in enumerate(lines, start=1)
        for host in _hosting_hosts_in(_fold(_decode(line)))
    ]


def check_no_hosting_links(content: str, source: str = "newsletter") -> None:
    """Raise HostingLinkError if the content carries a hosting address."""
    hits = find_hosting_links(content)
    if not hits:
        return
    listed = "\n".join(f"  line {number}: {host}" for number, host in hits)
    raise HostingLinkError(
        f"{source} links to a hosting address instead of policyengine.org:\n"
        f"{listed}\n"
        "Link the page's policyengine.org route instead (policyengine-app-v2's "
        "website/src/data/appZoneRoutes.ts lists them). If the route isn't live "
        "yet, get it live before the send, or cut the link."
    )


def main(paths: List[str]) -> int:
    """Print `line:host` for each hit in the given files; return 1 if any."""
    found = False
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            for number, host in find_hosting_links(f.read()):
                print(f"{number}:{host}")
                found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
