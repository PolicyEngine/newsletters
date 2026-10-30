"""Find hosting addresses that must never reach subscribers.

Public links go to policyengine.org, never to the address of the platform that
hosts a page (Max, 2026-10-29: "never share vercel links publicly - should
always be on policyengine.org, esp in newsletters"). A sent email can't be
corrected, and a hosting address can change with the next deploy.

The check reads the raw HTML line by line, after decoding HTML entities and
percent-escapes, so a host counts wherever a subscriber or their email client
could see or follow it: an href, an image src, link text, or a URL inside
another URL's query string. It reads each host the way a browser or reader
does: tabs and newlines inside a URL attribute such as href drop out, inline
tags such as <wbr> don't split the text, and Unicode dots, full-width letters
and invisible characters fold to plain ASCII.

Run as a script, it prints `line:host` for each hit and exits 1 if it finds any.
lint-newsletters.sh runs it that way, with src/ on PYTHONPATH.
"""

import html
import re
import sys
import unicodedata
from collections import Counter
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

# GitHub Pages sites of PolicyEngine and Axiom: their pages live at
# policyengine.org and axiom.org. Other people's github.io sites are their
# canonical addresses, so they stay linkable.
HOSTING_HOSTS = ("policyengine.github.io", "theaxiomfoundation.github.io")

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

# An attribute and its value, quoted or not. The lookbehind starts a name only
# at the start of a word, which keeps the scan linear.
ATTRIBUTE = re.compile(
    r"""(?<![^\s"'<>/=])([^\s"'<>/=]+)(\s*=\s*)"""
    r"""(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"""
)

# Attributes whose value a browser parses as a URL. Only there does it drop
# tabs and newlines (WHATWG URL standard); in alt or title text they stay
# breaks between words.
URL_ATTRIBUTES = frozenset(
    (
        "action",
        "background",
        "cite",
        "data",
        "formaction",
        "href",
        "imagesrcset",
        "longdesc",
        "lowsrc",
        "ping",
        "poster",
        "src",
        "srcset",
        "usemap",
        "xlink:href",
    )
)
URL_WHITESPACE = re.compile("[\t\n\r]")

# Inline tags don't break the text a reader sees: x.vercel<wbr>.app reads as
# x.vercel.app.
INLINE_TAG = re.compile(
    r"</?(?:a|abbr|b|bdi|bdo|big|cite|code|data|del|dfn|em|font|i|ins|kbd|mark|"
    r"q|s|samp|small|span|strike|strong|sub|sup|time|tt|u|var|wbr)(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)

# Characters a hostname drops: the UTS #46 ignored set (idna 3.20) and
# stringprep table B.1. They include the soft hyphen, zero-width spaces and
# joiners, invisible operators, fillers, variation selectors and the byte
# order mark.
IGNORED = re.compile(
    "[\u00ad\u034f\u115f\u1160\u17b4\u17b5\u1806\u180b-\u180f\u200b-\u200d"
    "\u2060-\u2064\u206a-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0"
    "\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0100-\U000e01ef]"
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
    letters, digits and dots, and the half-width ideographic stop into 。;
    browsers read 。 as a dot (UTS #46); and invisible characters drop out.
    """
    folded = unicodedata.normalize("NFKC", text).replace("\u3002", ".")
    return IGNORED.sub("", folded)


def _join_url_values(content: str) -> str:
    """Decode each URL attribute value and drop its tabs and newlines.

    A browser follows href="https://x.vercel.<newline>app" to x.vercel.app, so
    the check reads it that way too. Each raw newline removed goes back after
    the value, so every line outside it keeps its number, and a host inside a
    value that spans lines reports the line where the value starts. A value
    holding "<" ran past a missing closing quote into the markup after it, so it
    stays as it is.
    """

    def join(match: "re.Match[str]") -> str:
        name, equals, double, single, bare = match.groups()
        raw = next(value for value in (double, single, bare) if value is not None)
        if name.lower() not in URL_ATTRIBUTES or "<" in raw:
            return match.group(0)
        quote = '"' if double is not None else "'" if single is not None else ""
        value = URL_WHITESPACE.sub("", _decode(raw))
        return name + equals + quote + value + quote + "\n" * raw.count("\n")

    return ATTRIBUTE.sub(join, content)


def _hosting_hosts_in(text: str) -> List[str]:
    """Return the hosting hosts in one line of folded text, in order.

    Underscores at either end are Markdown emphasis, as in _vercel.app_. When
    both patterns flag a host, as with münchen.vercel.app and its ASCII tail
    nchen.vercel.app, only the outermost match counts.
    """
    found = {}
    for pattern in (HOST, ASCII_HOST):
        for match in pattern.finditer(text):
            host = match.group(1).lower().strip("_")
            if is_hosting_host(host):
                found[match.span(1)] = host
    hosts = []
    reach = -1
    for start, end in sorted(found, key=lambda span: (span[0], -span[1])):
        if end > reach:
            hosts.append(found[(start, end)])
            reach = end
    return hosts


def find_hosting_links(content: str) -> List[Tuple[int, str]]:
    """Return (line number, host) for each hosting address in the content."""
    hits = []
    lines = _join_url_values(content).split("\n")
    for number, line in enumerate(lines, start=1):
        hosts = _hosting_hosts_in(_fold(_decode(line)))
        # Add any host that only shows once inline tags drop out of the text.
        # It replaces the tail the raw line showed, as y.netlify.app does for
        # netlify.app in <b>y</b>.netlify.app.
        shown = _hosting_hosts_in(_fold(_decode(INLINE_TAG.sub("", line))))
        extra = list((Counter(shown) - Counter(hosts)).elements())
        for host in extra:
            tail = next((h for h in hosts if host.endswith("." + h)), None)
            if tail is not None:
                hosts.remove(tail)
        hits.extend((number, host) for host in hosts + extra)
    return hits


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
