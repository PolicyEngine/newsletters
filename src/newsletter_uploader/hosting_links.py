"""Find hosting addresses that must never reach subscribers.

Public links go to policyengine.org, never to the address of the platform that
hosts a page (Max, 2026-10-29: "never share vercel links publicly - should
always be on policyengine.org, esp in newsletters"). A sent email can't be
corrected, and a hosting address can change with the next deploy.

The check reads the raw HTML line by line, after decoding HTML entities and
percent-escapes, so a host counts wherever a subscriber or their email client
could see or follow it: an href, an image src, link text, or a URL inside
another URL's query string.

Run as a script, it prints `line:host` for each hit and exits 1 if it finds any.
lint-newsletters.sh runs it that way, with src/ on PYTHONPATH.
"""

import html
import re
import sys
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

# A host is one or more labels joined by dots, ending in a label of letters.
# The lookbehind stops a match starting inside a longer host or word.
HOST = re.compile(
    r"(?<![a-z0-9.-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})(?![a-z0-9-])",
    re.IGNORECASE,
)


class HostingLinkError(ValueError):
    """Raised when newsletter HTML carries a hosting address."""


def is_hosting_host(host: str) -> bool:
    """Return True if a subscriber must never see this host."""
    host = host.lower().rstrip(".")
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


def find_hosting_links(content: str) -> List[Tuple[int, str]]:
    """Return (line number, host) for each hosting address in the content."""
    hits = []
    for number, line in enumerate(content.splitlines(), start=1):
        for match in HOST.finditer(_decode(line)):
            host = match.group(1)
            if is_hosting_host(host):
                hits.append((number, host.lower()))
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
