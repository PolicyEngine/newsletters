#!/bin/bash
# Lint newsletter HTML files for common email compatibility issues

set -e

ERRORS=0
WARNINGS=0

# Editions dated on or after this day pin every raw.githubusercontent.com image
# to a full commit SHA (2026-09-08-us-v2.html was the first). Older editions
# use branch names, so the branch-name warning below skips them.
SHA_PINNED_FROM=20260908

echo "Checking newsletter HTML files..."

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
    # The match needs `src` to start an attribute (after whitespace or at the
    # start of a line), so `data-src=` and `?src=` inside a URL don't count.
    name="${file##*/}"
    if [[ "$name" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2}) ]]; then
        edition_date="${BASH_REMATCH[1]}${BASH_REMATCH[2]}${BASH_REMATCH[3]}"
    else
        edition_date=99999999
    fi
    if [ "$edition_date" -ge "$SHA_PINNED_FROM" ]; then
        unpinned=$(grep -noE "(^|[[:space:]])src[[:space:]]*=[[:space:]]*[\"']https://raw\.githubusercontent\.com/[^/\"']+/[^/\"']+/[^/\"']+/" "$file" \
            | grep -vE '/[0-9a-fA-F]{40}/$' \
            | sed -E 's/^([0-9]+:)[[:space:]]*/\1/' || true)
        if [ -n "$unpinned" ]; then
            echo "    ⚠️  WARNING: Image URL isn't pinned to a full 40-character commit SHA. Use the SHA of the pushed commit that added the image, not a branch name or main (see \"Images\" in CLAUDE.md)."
            echo "$unpinned"
            if [ -n "$GITHUB_ACTIONS" ]; then
                echo "::warning file=$file::Image URL isn't pinned to a full 40-character commit SHA (see \"Images\" in CLAUDE.md)."
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
