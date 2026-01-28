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

All newsletter HTML files follow this pattern:

1. **Inline Styles**: All styling is inline (required for email compatibility)
2. **Font**: Roboto loaded from Google Fonts
3. **Max Width**: 600px centered container
4. **Color Scheme**:
   - Primary blue: #2C6496
   - Teal accent: #39C6C0
   - Background grays: #F2F2F2, #D8E6F3, #F7FDFC
5. **Mailchimp Variables**: Footer includes merge tags like `*|EMAIL|*`, `*|UNSUB|*`, `*|UPDATE_PROFILE|*`
6. **Logo**: Links to PolicyEngine logo in main app repository on GitHub

## Creating New Newsletters

**IMPORTANT: Always start from the most recent newsletter as a template.** The template structure evolves over time, so copying from the latest edition ensures you use current styling, layout patterns, and best practices.

1. Find the most recent newsletter in `editions/` (sorted by date)
2. Copy it as a new file with date format: `YYYY-MM-DD-{audience}.html` (e.g., `2025-12-02-uk.html`)
3. Update content while maintaining:
   - Inline styles for email client compatibility
   - Responsive table layout in footer (Mailchimp CAN-SPAM compliance)
   - Mailchimp merge tags in footer
   - External assets use full URLs (no relative paths)

## Email Compatibility

### ⚠️ CRITICAL: All Images Must Use Absolute URLs

**NEVER use relative paths** like `../assets/images/...` or `./images/...` in newsletters.

Email clients fetch images from URLs - they cannot resolve relative paths. Always use absolute URLs:

```html
<!-- ❌ WRONG - will show broken image -->
<img src="../assets/images/dashboard.png">

<!-- ✅ CORRECT - absolute URL -->
<img src="https://raw.githubusercontent.com/PolicyEngine/newsletters/main/assets/images/dashboard.png">
```

For images on a feature branch, use the branch name:
```
https://raw.githubusercontent.com/PolicyEngine/newsletters/branch-name/assets/images/image.png
```

### Other Email Compatibility Rules

- **No CSS files**: All styles must be inline
- **Limited CSS**: Avoid modern CSS features (flexbox, grid)
- **Table layouts**: Use tables for complex layouts (email clients don't support modern layout)
- **No JavaScript**: Email clients block JavaScript
- **External images**: Use full URLs for all images
- **Responsive design**: Use media queries in `<style>` tags for mobile
- **Logo format**: SVG works in Mailchimp preview, but PNG is safer for broad email client compatibility
  - Current SVG URL works fine for most clients
  - Consider PNG for maximum compatibility (Outlook and some other clients block SVGs)

## File Naming Conventions

- Newsletter editions: `YYYY-MM-DD.html` (e.g., `2024-11-04.html`)
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

**IMPORTANT:** When making changes to a newsletter that has already been uploaded to Mailchimp, **update the existing campaign** instead of creating a new one. Use the Mailchimp API to update the campaign content:

```python
import requests

API_KEY = "your-api-key"
SERVER = "us5"  # from API key suffix
CAMPAIGN_ID = "existing-campaign-id"

url = f"https://{SERVER}.api.mailchimp.com/3.0/campaigns/{CAMPAIGN_ID}/content"
auth = ("anystring", API_KEY)

with open("editions/your-newsletter.html", "r") as f:
    html_content = f.read()

response = requests.put(url, auth=auth, json={"html": html_content})
```

To delete an accidentally created duplicate campaign:
```python
url = f"https://{SERVER}.api.mailchimp.com/3.0/campaigns/{CAMPAIGN_ID}"
requests.delete(url, auth=auth)
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
