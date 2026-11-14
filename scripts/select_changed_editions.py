"""Select changed editions without decoding Git's NUL-delimited filenames."""

import os
import re
import sys
from pathlib import Path


def main():
    """Reject misplaced social posts and write selected names as NUL-delimited bytes."""
    names = [name for name in Path(sys.argv[1]).read_bytes().split(b"\0") if name]
    misplaced = [
        name
        for name in names
        if re.search(rb"(^|/)[^/]*social[^/]*\.md$", name, re.IGNORECASE)
        and not name.startswith(b"editions/")
    ]
    if misplaced:
        print(
            "::error::social posts go in editions/ as <date>-<audience>-social.md, "
            "so their comparables can be checked:"
        )
        for name in misplaced:
            print(repr(os.fsdecode(name)))
        return 1

    selected = [
        name
        for name in names
        if name.lower().startswith(b"editions/")
        and name.lower().endswith((b".html", b".htm", b".md"))
    ]
    Path(sys.argv[2]).write_bytes(b"".join(name + b"\0" for name in selected))
    print("Changed editions:")
    for name in selected:
        print(repr(os.fsdecode(name)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
