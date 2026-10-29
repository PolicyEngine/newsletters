#!/bin/bash
# Lint newsletter HTML files for common email compatibility issues

set -e

ERRORS=0
WARNINGS=0

# Editions dated on or after this day pin every raw.githubusercontent.com image
# to a full commit SHA (2026-09-08-us-v2.html was the first). Older editions
# use branch names, so the branch-name warning below skips them.
SHA_PINNED_FROM=20260908
# Editions dated on or after this day may not link a hosting address such as
# *.vercel.app; public links go to policyengine.org (Max, 2026-10-29). Older
# editions went out as they are, so the error skips them.
HOSTING_CHECKED_FROM=20261030
SCRIPT_DIR="$(dirname "$0")"
PYTHON="$(command -v python3 || true)"

echo "Checking newsletter HTML files..."
if [ -z "$PYTHON" ]; then
    echo "  python3 not found, so the image-pinning warning and the hosting-address check are skipped."
fi

for file in editions/*.html; do
    echo "  Checking $file..."

    # Check for relative image paths (../  or ./ or just images/)
    if grep -qE 'src="\.\./' "$file" || grep -qE 'src="\./' "$file" || grep -qE 'src="[^h][^t][^t][^p].*\.(png|jpg|jpeg|gif|svg)"' "$file"; then
        echo "    ❌ ERROR: Relative image path found. Use absolute URLs (https://...)"
        grep -nE 'src="\.\./' "$file" || true
        grep -nE 'src="\./' "$file" || true
        ERRORS=$((ERRORS + 1))
    fi

    # Check for refs/heads/ in URLs - causes rendering issues in Mailchimp
    if grep -q 'refs/heads/' "$file"; then
        echo "    ❌ ERROR: URL contains refs/heads/, which can break in Mailchimp. Pin raw.githubusercontent.com URLs to a full 40-character commit SHA instead (see \"Images\" in CLAUDE.md)."
        grep -n 'refs/heads/' "$file"
        ERRORS=$((ERRORS + 1))
    fi

    # Warn when a newer edition loads an image from a branch name, `main` or a
    # short SHA rather than a full commit SHA. Undated files count as newer.
    # unpinned_images.py reads the src attributes with an HTML parser.
    name="${file##*/}"
    if [[ "$name" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
        edition_date="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}"
    else
        edition_date=99999999
    fi
    # Fail a newer edition that links a hosting address instead of
    # policyengine.org. hosting_links.py decodes entities and percent-escapes
    # and prints `line:host` for each hit.
    if [ "$edition_date" -ge "$HOSTING_CHECKED_FROM" ] && [ -n "$PYTHON" ]; then
        hosting=$(PYTHONPATH="$SCRIPT_DIR/../src" "$PYTHON" -m newsletter_uploader.hosting_links "$file") || true
        if [ -n "$hosting" ]; then
            echo "    ❌ ERROR: Link to a hosting address. Public links go to the page's policyengine.org route, never *.vercel.app, policyengine.github.io or another hosting address (see \"Links\" in CLAUDE.md)."
            echo "$hosting"
            if [ -n "$GITHUB_ACTIONS" ]; then
                while IFS= read -r entry; do
                    echo "::error file=$file,line=${entry%%:*}::Links ${entry#*:}, a hosting address. Link the policyengine.org route instead (see \"Links\" in CLAUDE.md)."
                done <<< "$hosting"
            fi
            ERRORS=$((ERRORS + 1))
        fi
    fi

    if [ "$edition_date" -ge "$SHA_PINNED_FROM" ] && [ -n "$PYTHON" ]; then
        unpinned=$("$PYTHON" "$SCRIPT_DIR/unpinned_images.py" "$file") || unpinned=""
        if [ -n "$unpinned" ]; then
            echo "    ⚠️  WARNING: Image URL isn't pinned to a full 40-character commit SHA. Use the SHA of the pushed commit that added the image, not a branch name or main (see \"Images\" in CLAUDE.md)."
            echo "$unpinned"
            if [ -n "$GITHUB_ACTIONS" ]; then
                while IFS= read -r entry; do
                    echo "::warning file=$file,line=${entry%%:*}::Image URL isn't pinned to a full 40-character commit SHA (see \"Images\" in CLAUDE.md)."
                done <<< "$unpinned"
            fi
            WARNINGS=$((WARNINGS + 1))
        fi
    fi

done

if [ $WARNINGS -gt 0 ]; then
    echo ""
    echo "⚠️  Found $WARNINGS warning(s). These don't fail the lint."
fi

if [ $ERRORS -gt 0 ]; then
    echo ""
    echo "❌ Found $ERRORS error(s). Please fix before committing."
    exit 1
else
    echo ""
    echo "✅ All newsletter files passed lint checks."
fi
