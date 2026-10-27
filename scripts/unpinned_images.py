"""Print the images in an edition that aren't pinned to a full commit SHA.

Used by lint-newsletters.sh. Prints `line:url` for each `src` attribute that
loads from raw.githubusercontent.com at a ref other than a full 40-character
commit SHA, such as a branch name, `main` or a short SHA. It reads attributes
with an HTML parser, so `SRC=`, spaces or newlines around `=`, and `src=` text
inside another attribute's value are handled the way an email client sees them.
"""

import re
import sys
from html.parser import HTMLParser

RAW_URL = re.compile(
    r"^https?://raw\.githubusercontent\.com/[^/]+/[^/]+/([^/]+)/", re.IGNORECASE
)
FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


class UnpinnedImageFinder(HTMLParser):
    """Collect (line, url) for each unpinned raw.githubusercontent.com src."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.unpinned = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name != "src" or not value:
                continue
            url = value.strip()
            match = RAW_URL.match(url)
            if match and not FULL_SHA.match(match.group(1)):
                self.unpinned.append((self.getpos()[0], url))


def main(path):
    finder = UnpinnedImageFinder()
    with open(path, encoding="utf-8", errors="replace") as f:
        finder.feed(f.read())
    finder.close()
    for line, url in finder.unpinned:
        print(f"{line}:{url}")


if __name__ == "__main__":
    main(sys.argv[1])
