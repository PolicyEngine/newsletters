---
description: Preview newsletter HTML with screenshots and validation checks
argument-hint: <html-file>
---

Open the newsletter in a browser, capture screenshots, and validate email compatibility.

## Usage

```bash
/preview-newsletter editions/2025-10-02-uk.html
```

## Process

Use the `newsletter-previewer` subagent to:

1. **Open in browser** - Display the HTML for visual review
2. **Capture screenshots** - Desktop (700px, wider than the template's 620px mobile breakpoint) and mobile (320px) views
3. **Validate compatibility** - Check for email client issues
4. **Review content** - Verify links, images, styling

## What Gets Checked

**Email Compatibility:**
- Inline styles, apart from the mobile `<style>` block and the Google Fonts `<link>`
- 600px max width
- No modern CSS features or CSS variables
- Table-based layouts
- Full image URLs pinned to a commit SHA, not a branch name or `main`
- A solid `background-color` behind each gradient
- Hidden preheader matches the campaign's preview text
- All four Mailchimp merge tags present

**Visual Quality:**
- Logo renders
- Colors match the palette in `CLAUDE.md` (Inter, teal, dark `#0F1419` page)
- Buttons styled correctly (teal `#319795`)
- Text readable and properly spaced
- White sections separated by `#E2E8F0` dividers

**Content:**
- All links valid and working
- Images load correctly
- Headers use sentence case
- Professional tone (no inappropriate emoji)

## Output

Shows screenshots and validation report:
```
# Newsletter Preview Report

## Screenshots
[Desktop and mobile screenshots]

## Validation Results
✓ All email compatibility checks pass
✗ Warning: [any issues found]

## Recommendations
- [Suggested improvements]
```

## When to Use

- Before uploading to Mailchimp
- After making styling changes
- To verify cross-client compatibility
- Before scheduling a send
