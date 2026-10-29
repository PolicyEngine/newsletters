# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a simple newsletter repository containing HTML email templates for PolicyEngine's Mailchimp campaigns. No build tools, testing frameworks, or development servers are needed - this is pure HTML/CSS.

## Repository Structure

```
newsletters/
├── editions/          # Newsletter HTML files (one per edition)
│   ├── 2024-10-29.html
│   └── 2024-11-04.html
├── assets/
│   ├── images/       # Newsletter image assets
│   └── styles.css    # Shared CSS (currently unused)
├── config/
│   └── mailchimp-settings.json  # API key configuration (not committed)
└── README.md
```

## Newsletter Template Structure

This describes the current template as used by the two latest editions, `editions/2026-10-20-uk.html` (#28) and `editions/2026-10-26-uk.html` (#31). Editions from `2025-11-26-uk-prebudget.html` on use Inter and the teal palette, except `2025-12-08-uk-autumn-budget.html`. Editions before that use Roboto (except `2024-03-28.html`, which uses Helvetica Neue), most with a blue palette (`#2C6496`), so don't copy from them.

### Head

- `<!DOCTYPE html>`, `<html lang="en">`, UTF-8 and viewport metas, and a `<title>` of the form `PolicyEngine UK &middot; 27 October 2026` (send date, British format).
- **Font: Inter** from Google Fonts:
  ```html
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  ```
  `<body>` sets `font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;` so clients that ignore the `<link>`, such as Gmail, use a system sans. Classic Outlook for Windows (2007–2016) is the exception: caniemail notes that it ignores the stack for a font declared with `@font-face` and falls back to Times New Roman unless `mso-font-alt` sets the fallback, and neither edition sets it. The `h1` and the card `h2` ask for `font-weight:800`, which the link doesn't load, so they render at 700 where Inter loads; add `800` to `wght@` if you want the heavier weight.
- **Mobile media query**: apart from the font `<link>`, the only CSS outside inline `style` attributes is one block in `<head>`. It overrides inline values with `!important`, keyed to classes on the container table, its cells and the headings:
  ```html
  <style type="text/css">
    @media only screen and (max-width: 620px) {
      .container { width: 100% !important; }
      .outer-pad { padding: 20px 6px !important; }
      .hero-pad { padding: 28px 18px 24px 18px !important; }
      .section-pad { padding: 28px 18px !important; }
      .hero-title { font-size: 24px !important; line-height: 1.15 !important; }
    }
  </style>
  ```
  That is the block in `2026-10-26-uk.html`. `2026-10-20-uk.html` also has `.card-pad { padding: 22px 18px !important; }` and `.h2 { font-size: 21px !important; }` for its feature card, plus `.col-stack` / `.col-spacer` rules for two-column rows that it doesn't use. Keep the rules for the classes your edition uses.

### Layout, top to bottom

The layout is nested tables with inline styles.

1. `<body>` with `margin:0;padding:0;background-color:#0F1419;` and the font stack above.
2. **Hidden preheader**, first thing in `<body>`: `<div style="display:none;max-height:0;overflow:hidden;">…</div>`. See the preview-text note below.
3. An outer full-width table (`background-color:#0F1419`) whose centred cell (`class="outer-pad"`, `padding:32px 12px`) holds the `class="container"` table: `width="600"` and `style="max-width:600px;width:100%;"`.
4. **Header row**: the white PolicyEngine logo PNG on the left (`height:24px;width:auto;opacity:0.9;`) and the send date on the right (`11px`, weight 500, uppercase, `letter-spacing:0.1em`, `#4FD1C5`), e.g. `27 October 2026`.
5. **Hero** (`class="hero-pad"`, `padding:48px 40px 40px 40px`, `border-radius:16px 16px 0 0`): `background: linear-gradient(165deg, #1D4044 0%, #234E52 40%, #285E61 100%); background-color:#234E52;`. Inside: a 48×3px accent bar (`linear-gradient(90deg, #4FD1C5 0%, #81E6D9 100%)`), the `h1` (`class="hero-title"`, 28px, weight 800, `#FFFFFF`, `letter-spacing:-0.02em`) and one standfirst paragraph (15px, `#B2F5EA`).
6. **Sections**: one `<tr><td class="section-pad">` per item, `background-color:#FFFFFF;padding:28px 40px;border-bottom:1px solid #E2E8F0;`. A section can hold:
   - an eyebrow label: 10px, weight 700, uppercase, `letter-spacing:0.15em`, `#319795` (e.g. `Online webinar &middot; Wednesday 28 October`);
   - a title paragraph: 16px, weight 700, `#1D4044`;
   - body paragraphs: 13px, `line-height:1.6`, `#475569`;
   - a "What we find" list: an 11px uppercase `#319795` label, then a table of rows, each a 16px-wide `&bull;` cell and a 12px `#475569` text cell, with figures in `<strong style="color:#1D4044;">`;
   - a linked image: `width="520"` and `style="width:100%;max-width:520px;height:auto;display:block;border-radius:8px;border:1px solid #E2E8F0;margin:0 0 16px 0;"`, with `alt` text that states what the image shows, figures included;
   - a centred button: `<div style="text-align:center;"><a href="…" style="display:inline-block;padding:12px 24px;background-color:#319795;color:#FFFFFF;text-decoration:none;font-weight:600;font-size:14px;border-radius:6px;">Register for the webinar &rarr;</a></div>`.
7. **Feature card** (optional; the JOSS paper in `2026-10-20-uk.html`): inside a section cell, a table with the hero's gradient and `background-color:#234E52`, `border-radius:12px`, and a `class="card-pad"` cell (`padding:28px 28px`). Eyebrow 11px `#81E6D9`; `h2` (`class="h2"`) 20px, weight 800, `#FFFFFF`; body 14px `#B2F5EA`; image up to 472px wide on a white background.
8. **Inline links** in body text: `color:#319795;font-weight:600;text-decoration:none;`, ending `&nbsp;&rarr;`.
9. **Sign-off**: the last white cell, also `class="section-pad"`, with `padding:32px 40px;border-radius:0 0 16px 16px;`: `Best wishes,<br>` then `The PolicyEngine Team` in `#1D4044`, weight 600.
10. **Footer**, on the dark background below the white sections:
    - a centred row of links, 12px, weight 500, `#81E6D9`, `margin:0 16px`: X (`https://x.com/ThePolicyEngine`), LinkedIn (`https://www.linkedin.com/company/thepolicyengine`) and Website (`https://www.policyengine.org/uk` in UK editions);
    - the Mailchimp merge tags, centred, 11px, `#64748B`. Keep all four:
      ```html
      This email was sent to <a href="mailto:*|EMAIL|*" style="color:#64748B;">*|EMAIL|*</a><br>
      <a href="*|UNSUB|*" style="color:#64748B;">Unsubscribe</a> &middot; <a href="*|UPDATE_PROFILE|*" style="color:#64748B;">Update preferences</a><br>
      <span style="color:#4B5563;">*|LIST:ADDRESSLINE|*</span>
      ```

### Palette

Hard-code these hex values inline. Don't use CSS variables: caniemail lists Gmail as unable to declare custom properties and most Outlook clients as not supporting them. Most values are `@policyengine/ui-kit` tokens (`src/theme/tokens.css`), named here so new shades come from the same scales.

| Hex | ui-kit token | Used for |
|---|---|---|
| `#0F1419` | none | page background (`<body>` and outer table) |
| `#1D4044` | `--color-teal-900` | gradient start; section titles, `<strong>` figures, sign-off name |
| `#234E52` | `--color-teal-800` | gradient middle; the solid `background-color` behind the hero and card gradients |
| `#285E61` | `--color-teal-700` | gradient end |
| `#319795` | `--color-teal-500` | eyebrow labels, "What we find" labels, buttons, inline links |
| `#4FD1C5` | `--color-teal-300` | header date; accent bar start |
| `#81E6D9` | `--color-teal-200` | accent bar end; card eyebrow; footer social links |
| `#B2F5EA` | `--color-teal-100` | text on the hero and the card |
| `#FFFFFF` | none on the scales (semantic `--background`, `--card`) | section backgrounds; headings on dark; button text |
| `#475569` | `--color-gray-600` | body text |
| `#E2E8F0` | `--color-gray-200` | section dividers, image borders |
| `#64748B` | `--color-gray-500` | footer text and links |
| `#4B5563` | none | footer postal address (`*|LIST:ADDRESSLINE|*`) |

### Images

Every `src` is an absolute `raw.githubusercontent.com` URL pinned to a full 40-character commit SHA, never a branch name:

- **Edition images**: `https://raw.githubusercontent.com/PolicyEngine/newsletters/<commit-sha>/assets/images/<name>.png`. Both latest editions use `43919d6d0b6509a0407203fa7f268e90f9122968`, the commit that added the 20 October images. A commit can't contain its own SHA, so commit and push the images first, then point the HTML at that commit (#28 did this in `646f901`).
- **Logo**: the white PNG from policyengine-app-v2, pinned the same way: `https://raw.githubusercontent.com/PolicyEngine/policyengine-app-v2/2e38710033e846461217291328a3748d1cd45de7/app/public/assets/logos/policyengine/white.png`.

A branch URL stops working once the branch is deleted after merge, and a `main` URL changes if the file is replaced later. A pinned URL keeps showing what was sent.

### Notes for new editions

These came from the independent review of #31 (2026-10-27).

- **Make the hidden preheader match the campaign's preview text.** The preheader `<div>` text must be the same words as the Mailchimp campaign's preview text (the uploader's `--preview`, or the preview set in Mailchimp). If you change one, change the other. In #31 they differed: the file says "On Budget day at 4:30pm, we'll present our first estimates and take your questions." while the campaign's preview was "We'll present our first estimates on Budget day and take your questions."
- **Give every `linear-gradient` a solid `background-color` fallback.** caniemail lists no `linear-gradient` support in any Outlook client at the latest version it tested: Windows desktop 2007–2019 (where gradients need VML), Windows Mail, Outlook.com, and the Mac, iOS and Android apps. Without a fallback the element has no background there. The hero and the feature card already do this: `background: linear-gradient(...); background-color:#234E52;`. Put `background-color` after the `background` shorthand, because the shorthand resets it. The hero's 48×3px accent bar has no fallback in either edition, so it doesn't show in Outlook. Don't just add `background-color` to it: caniemail says classic Outlook for Windows ignores `width` and `height` on a `<div>`, so the colour would likely spread across the hero (untested). To give it one, rebuild it as a 48×3 table cell with `bgcolor` and `font-size:0;line-height:0;`, and test that in Outlook before sending.

### Links

Every link goes to policyengine.org, never to the address of the platform that hosts a page (Max, 2026-10-29: "never share vercel links publicly - should always be on policyengine.org, esp in newsletters"). A sent email can't be corrected.

- **Never link** `*.vercel.app`, `vercel.com`, `policyengine.github.io`, `*.netlify.app`, `*.pages.dev`, `*.modal.run`, `*.run.app` or `*.appspot.com`. Dashboards and microsites live at their policyengine.org route, for example `https://www.policyengine.org/us/ballot-measures-2026`. `website/src/data/appZoneRoutes.ts` in policyengine-app-v2 lists every route.
- **Curl each route for 200 before you upload.** If a route isn't live yet, get its appZoneRoutes PR merged and deployed before the send, or cut the link. Never swap in the Vercel URL to make a link work: that is how `2026-10-29-us.html` went out with seven `ballot-measures-2026.vercel.app` links.
- Other people's sites stay as they are, including their own `github.io` pages (for example `fhoces.github.io`).
- **Enforced:**
  - `upload-newsletter` refuses HTML that links any of these hosts. It runs the check before it calls Mailchimp, for new campaigns and for `--campaign-id` updates, so nothing reaches Mailchimp.
  - The CI lint fails any edition dated 2026-10-30 or later that links one.
  - The check (`src/newsletter_uploader/hosting_links.py`) decodes HTML entities and percent-escapes. It also counts a host that shows only as link text.
- A reviewed exception goes in `ALLOWED_HOSTS` in that file.

## Creating New Newsletters

**IMPORTANT: Always start from the most recent newsletter as a template.** The template structure evolves over time, so copying from the latest edition ensures you use current styling, layout patterns, and best practices.

1. Find the most recent newsletter in `editions/` (sorted by date)
2. Copy it as a new file with date format: `YYYY-MM-DD-{audience}.html` (e.g., `2025-12-02-uk.html`)
3. Update content while maintaining:
   - Inline styles for email client compatibility
   - Responsive table layout in footer (Mailchimp CAN-SPAM compliance)
   - Mailchimp merge tags in footer
   - External assets use full URLs pinned to a commit SHA (no relative paths; see "Images" above)
   - The hidden preheader matches the campaign's preview text
   - Every link goes to policyengine.org, never a hosting address (see "Links" above)

## Email Compatibility

### ⚠️ CRITICAL: All Images Must Use Absolute URLs

**NEVER use relative paths** like `../assets/images/...` or `./images/...` in newsletters.

Email clients fetch images from URLs - they cannot resolve relative paths. Always use absolute URLs:

```html
<!-- ❌ WRONG - will show broken image -->
<img src="../assets/images/dashboard.png">

<!-- ✅ CORRECT - absolute URL pinned to the commit that added the image -->
<img src="https://raw.githubusercontent.com/PolicyEngine/newsletters/<commit-sha>/assets/images/dashboard.png">
```

Use a full commit SHA, not a branch name or `main`; see "Images" under "Newsletter Template Structure".

### Other Email Compatibility Rules

- **No CSS files**: styles are inline, apart from the mobile media-query `<style>` block and the Google Fonts `<link>` in `<head>`
- **Limited CSS**: Avoid modern CSS features (flexbox, grid)
- **Table layouts**: Use tables for complex layouts (email clients don't support modern layout)
- **No JavaScript**: Email clients block JavaScript
- **External images**: Use full URLs for all images
- **Responsive design**: Use media queries in `<style>` tags for mobile
- **Logo format**: use the PNG logo (the template's `white.png`), not SVG; Outlook and some other clients block SVGs

## File Naming Conventions

- Newsletter editions: `YYYY-MM-DD-{audience}.html` (e.g., `2026-10-20-uk.html`). The file name carries the planned date and isn't renamed if the send moves; the `<title>` and header carry the send date (`2026-10-20-uk.html` is dated 21 October, `2026-10-26-uk.html` 27 October).
- Images: Descriptive names in `assets/images/`

## Configuration

- `config/mailchimp-settings.json` contains API key (gitignored, template provided)
- `.env` file contains `MAILCHIMP_API_KEY` for the upload script
- No build configuration needed

## Uploading to Mailchimp

This repo includes a Python package (`newsletter_uploader`) with full test coverage.

### Installation

```bash
pip install -e ".[dev]"
export MAILCHIMP_API_KEY="your-key-us5"
```

### Usage

```bash
# UK subscribers only
upload-newsletter editions/2025-10-01-uk.html \
  --audience uk \
  --subject "UK Happy Hour Tomorrow + New Research" \
  --preview "Join us for drinks and discussion"

# US (non-UK) subscribers
upload-newsletter editions/2025-01-15-us.html \
  --audience us \
  --subject "New US Policy Analysis" \
  --preview "Latest research on tax reforms"

# All subscribers
upload-newsletter editions/2025-01-01-global.html \
  --audience all \
  --subject "PolicyEngine Year in Review" \
  --preview "Our 2024 impact and progress"
```

**Audience targeting:**
- `--audience uk` - Only UK subscribers (COUNTRY = "United Kingdom")
- `--audience us` - All non-UK subscribers (COUNTRY ≠ "United Kingdom") - includes US and missing country data
- `--audience all` - All subscribers (no filtering)

The command creates a **draft campaign** (not sent) that you can review, test, and send from the Mailchimp web interface.

### Updating Existing Drafts

**IMPORTANT:** When making changes to a newsletter that has already been uploaded to Mailchimp, **update the existing campaign** instead of creating a new one. Use `upload-newsletter` with `--campaign-id`, which runs the same checks as a new upload (see "Links"):

```bash
upload-newsletter editions/your-newsletter.html \
  --campaign-id existing-campaign-id \
  --subject "Same subject" \
  --preview "Same preview text as the hidden preheader"
```

Don't PUT the HTML to Mailchimp's `/content` endpoint yourself; that skips the checks.

To delete an accidentally created duplicate campaign:
```python
import requests

API_KEY = "your-api-key"
SERVER = "us5"  # from API key suffix
CAMPAIGN_ID = "duplicate-campaign-id"

url = f"https://{SERVER}.api.mailchimp.com/3.0/campaigns/{CAMPAIGN_ID}"
requests.delete(url, auth=("anystring", API_KEY))
```

### Development

```bash
# Run tests (93% coverage)
pytest -v

# Format and lint
black src/ tests/
ruff check src/ tests/
```

The package is structured with:
- `src/newsletter_uploader/` - Core package modules
- `tests/` - Comprehensive test suite
- CI runs on GitHub Actions for Python 3.8-3.11

## Claude Code Automations

Custom subagents and slash commands for newsletter workflow (see `.claude/README.md` for details):

**Subagents:**
- `newsletter-writer` - Converts research posts to newsletter HTML sections
- `campaign-analyzer` - Analyzes Mailchimp performance data

**Slash Commands:**
- `/create-newsletter --posts post1,post2 --event event-slug --audience uk`
- `/campaign-stats 2024-10-29`
- `/sync-countries`
- `/upload-draft editions/file.html --audience uk --subject "..." --preview "..."`

Example workflow:
```bash
# Generate newsletter from research posts
/create-newsletter --posts uk-carbon-tax,uk-vat --event nov-3-london --audience uk

# Upload to Mailchimp
/upload-draft editions/2025-10-02-uk.html --audience uk --subject "..." --preview "..."

# Check performance later
/campaign-stats 2025-10-02
```
